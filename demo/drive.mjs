/* Drives a full conversation through the real UI in a headless browser.
 *
 *   node demo/drive.mjs                 # screenshots only, into demo/shots
 *   node demo/drive.mjs --video         # also records demo/raw/*.webm
 *
 * Used twice: as a visual smoke test of the frontend, and as the capture pass
 * for the demo video. Requires the backend on http://127.0.0.1:8000.
 */

import { chromium } from "playwright";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const SHOTS = path.join(ROOT, "demo", "shots");
const RAW = path.join(ROOT, "demo", "raw");
const VIDEO = process.argv.includes("--video");
const URL = process.env.DEMO_URL || "http://127.0.0.1:8000/";

mkdirSync(SHOTS, { recursive: true });
mkdirSync(RAW, { recursive: true });

/* The demo conversation. Ordered to hit, in one unbroken call: Hinglish
 * mirroring, a published price, a discount objection, an unknown fact, a
 * booking that FAILS on a full slot, recovery, a confirmed booking, and a
 * clean close. `shot` names a screenshot to take after the agent replies. */
const SCRIPT = [
  { text: "Hi, Sector 79 wala project ke bare mein jaanna tha", shot: "01-hinglish" },
  { text: "3 BHK chahiye, family ke liye. Price kya hai?", shot: "02-price" },
  { text: "Thoda discount kar do na, best price bata do", shot: "03-discount" },
  { text: "Achha carpet area aur possession date kya hai?", shot: "04-unknown" },
  { text: "Theek hai, site visit karte hain. Saturday 11 baje", shot: "05-visit" },
  { text: "Rohit Sharma, 9811122233", shot: "06-details" },
  { text: "Haan confirm kar do", shot: "07-booking-failed" },
  { text: "Chalo Saturday 3 baje kar do", shot: "08-retry" },
  { text: "Haan bilkul, confirm", shot: "09-booked" },
  { text: "Thank you, bye", shot: "10-closed" },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Pace the capture to the voiceover. Without this the recording is about fifty
 * seconds against three minutes of narration, and the edit has to freeze-pad
 * most of it. Reading the real per-beat durations means the footage already
 * matches and the picture keeps moving while the narrator talks. */
const VO_TIMINGS = path.join(ROOT, "demo", "vo", "timings.json");
const voDuration = existsSync(VO_TIMINGS)
  ? Object.fromEntries(
      JSON.parse(readFileSync(VO_TIMINGS, "utf8")).map((t) => [t.beat, t.duration]))
  : {};

/* Sit on a beat until its narration would have finished. Scrolls the given
 * pane a little at a time so a long beat is not a frozen screenshot. */
async function holdBeat(page, name, startedAt, selector) {
  const target = (voDuration[name] ?? 3) * 1000 + 400;
  const deadline = startedAt + target;
  while (Date.now() < deadline) {
    const left = deadline - Date.now();
    if (selector && left > 1400) {
      await page.locator(selector).evaluate((n) => { n.scrollTop += 46; })
        .catch(() => {});
    }
    await sleep(Math.min(320, Math.max(60, left)));
  }
}

/* Type at a human cadence so the recording does not look scripted. */
async function humanType(page, text) {
  await page.click("#input");
  for (const ch of text) {
    await page.keyboard.type(ch, { delay: 0 });
    await sleep(12 + Math.floor(Math.random() * 22));
  }
  await sleep(320);
}

const b = await chromium.launch();
const SIZE = VIDEO ? { width: 1920, height: 1080 } : { width: 1600, height: 900 };
const ctx = await b.newContext({
  viewport: SIZE,
  deviceScaleFactor: VIDEO ? 1 : 2,
  colorScheme: "light",
  reducedMotion: "no-preference",
  ...(VIDEO ? { recordVideo: { dir: RAW, size: SIZE } } : {}),
});

/* Beat markers: wall-clock offsets from the first frame, so the edit can slice
 * the recording per narration beat and pad each slice to the voiceover length. */
const t0 = Date.now();
const beats = [];
const mark = (name) => beats.push({ name, t: (Date.now() - t0) / 1000 });

const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(`PAGEERROR ${e.message}`));

await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector("#conn-status[data-state='ok']", { timeout: 20000 });
mark("intro");
const introAt = Date.now();
await page.screenshot({ path: path.join(SHOTS, "00-idle.png") });
if (VIDEO) await holdBeat(page, "intro", introAt, ".rail");
else await sleep(600);

for (const step of SCRIPT) {
  // The agent decides when the conversation is over, so it can close earlier
  // than the script expects. Stop feeding it messages once it has.
  if (await page.locator("#input").isDisabled()) {
    console.warn(`agent closed the conversation before: ${step.text}`);
    break;
  }
  mark(step.shot);
  // Count only settled agent output. The typing placeholder is also a
  // .msg.agent, so counting it would satisfy the wait before the reply lands.
  const settled = '.msg.agent:not([data-typing]), .annot';
  const before = await page.locator(settled).count();
  await humanType(page, step.text);
  await page.keyboard.press("Enter");
  // Wait for the agent's turn to land (a new bubble or a redline annotation).
  await page
    .waitForFunction(
      ([sel, n]) => document.querySelectorAll(sel).length > n,
      [settled, before],
      { timeout: 90000 }
    )
    .catch(() => console.warn(`timed out waiting after: ${step.text}`));
  await page.screenshot({ path: path.join(SHOTS, `${step.shot}.png`) });
  if (VIDEO) await holdBeat(page, step.shot, beatStart, null);
  else await sleep(400);
}

// Close out: generate the lead record and let it settle on screen. If the agent
// has not closed the conversation itself, end it by hand so the demo always
// reaches the payoff.
if (!(await page.locator("#analytics-btn").isVisible())) {
  await page.click("#end-btn");
}
{
  await sleep(VIDEO ? 800 : 200);
  mark("analytics");
  await page.click("#analytics-btn");
  const analyticsAt = Date.now();
  await page.waitForSelector(".dossier-groups", { timeout: 90000 });
  await page.screenshot({ path: path.join(SHOTS, "11-analytics.png") });
  if (VIDEO) await holdBeat(page, "analytics", analyticsAt, ".dossier");
  else await sleep(600);
  mark("json");
  const jsonAt = Date.now();
  await page.locator("details.raw summary").click();
  if (VIDEO) await holdBeat(page, "json", jsonAt, ".dossier");
  else await sleep(400);
  await page.screenshot({ path: path.join(SHOTS, "12-json.png"), fullPage: !VIDEO });
}

mark("outro");
const outroAt = Date.now();
if (VIDEO) await holdBeat(page, "outro", outroAt, ".log");
await ctx.close();
await b.close();

if (errors.length) {
  console.error("CONSOLE ERRORS:\n" + errors.join("\n"));
  process.exit(1);
}
if (VIDEO) {
  const { writeFileSync } = await import("node:fs");
  writeFileSync(path.join(RAW, "beats.json"), JSON.stringify(beats, null, 2));
}
console.log(`done — screenshots in demo/shots${VIDEO ? ", video + beats.json in demo/raw" : ""}`);
