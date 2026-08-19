/* Northstar One agent console.
   Static, no build step, no dependencies. Talks to the FastAPI backend over
   three endpoints: /api/config, /api/chat, /api/analytics.

   The page never hardcodes a price. Everything in the spec rail comes from
   /api/config, so the UI cannot drift away from the agent's knowledge base. */

const $ = (sel) => document.querySelector(sel);

const el = {
  log: $("#log"),
  form: $("#composer"),
  input: $("#input"),
  send: $("#send"),
  status: $("#conn-status"),
  model: $("#model-name"),
  spec: $("#spec-list"),
  probes: $("#probes"),
  events: $("#events"),
  endedBar: $("#ended-bar"),
  endedOutcome: $("#ended-outcome"),
  analyticsBtn: $("#analytics-btn"),
  analyticsSlot: $("#analytics-slot"),
  resetBtn: $("#reset-btn"),
  endBtn: $("#end-btn"),
  settings: $("#settings"),
  settingsBtn: $("#settings-btn"),
  apiBase: $("#api-base"),
};

/* ── Endpoint resolution ───────────────────────────────────────────────
   Priority: ?api= in the URL, then a saved value, then the page's own origin
   (true when FastAPI serves this file), then a local dev backend. GitHub Pages
   hits the last two, which is why the endpoint box exists. */
const DEFAULT_LOCAL = "http://127.0.0.1:8000";

function resolveBase() {
  const fromQuery = new URLSearchParams(location.search).get("api");
  if (fromQuery) localStorage.setItem("northstar.api", fromQuery.replace(/\/$/, ""));
  const saved = localStorage.getItem("northstar.api");
  if (saved) return saved;
  const selfHosted = location.protocol.startsWith("http") &&
                     !location.hostname.endsWith("github.io");
  return selfHosted ? location.origin : DEFAULT_LOCAL;
}

let API = resolveBase();
let sessionId = null;
let ended = false;
let busy = false;

/* ── Rendering ─────────────────────────────────────────────────────────── */

function scroll() {
  el.log.scrollTop = el.log.scrollHeight;
}

function addMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "user" ? "You" : "Meera · Northstar Homes";
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;
  wrap.append(who, body);
  el.log.append(wrap);
  scroll();
  return wrap;
}

function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg agent";
  wrap.dataset.typing = "1";
  wrap.innerHTML =
    '<div class="who">Meera · Northstar Homes</div>' +
    '<div class="body"><span class="typing"><i></i><i></i><i></i></span></div>';
  el.log.append(wrap);
  scroll();
  return wrap;
}

/* One vocabulary for tool events, used both inline and in the dossier. */
function describeEvent(ev) {
  const r = ev.result || {};
  if (ev.type === "booking") {
    if (r.status === "confirmed") {
      return { ok: true, key: "Booking confirmed",
               detail: `${r.booking_id} · ${r.day} ${r.date} · ${r.time_slot}` };
    }
    return { ok: false, key: "Booking failed", detail: `${r.reason} — ${r.message}` };
  }
  if (ev.type === "escalation") {
    return { ok: false, key: "Escalated to human",
             detail: `${r.ticket_id} · ${r.reason || "requested"}` };
  }
  if (ev.type === "end") {
    return { ok: r.outcome === "site_visit_booked",
             key: "Conversation ended", detail: r.outcome || "" };
  }
  return { ok: false, key: ev.type, detail: JSON.stringify(r) };
}

function addAnnotation(ev) {
  const { ok, key, detail } = describeEvent(ev);
  const div = document.createElement("div");
  div.className = `annot${ok ? " ok" : ""}`;
  div.innerHTML = `<span class="k"></span> <span class="d"></span>`;
  div.querySelector(".k").textContent = key;
  div.querySelector(".d").textContent = detail;
  el.log.append(div);
  scroll();

  const empty = el.events.querySelector(".empty");
  if (empty) empty.remove();
  const li = document.createElement("li");
  li.innerHTML = `<span class="k"></span> <span></span>`;
  li.querySelector(".k").className = ok ? "k ok" : "k";
  li.querySelector(".k").textContent = key;
  li.querySelectorAll("span")[1].textContent = detail;
  el.events.append(li);
}

function addError(text) {
  const div = document.createElement("div");
  div.className = "annot";
  div.innerHTML = `<span class="k">Error</span> <span></span>`;
  div.querySelectorAll("span")[1].textContent = text;
  el.log.append(div);
  scroll();
}

/* ── Talking to the backend ────────────────────────────────────────────── */

async function api(path, options) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { detail = (await res.json()).detail || detail; } catch { /* keep status */ }
    throw new Error(detail);
  }
  return res.json();
}

function setBusy(state) {
  busy = state;
  el.send.disabled = state || ended;
  el.input.disabled = ended;
  el.status.dataset.state = state ? "busy" : "ok";
  el.status.textContent = state ? "thinking" : "connected";
}

async function send(text) {
  if (!text.trim() || busy || ended) return;
  addMessage("user", text);
  el.input.value = "";
  el.input.style.height = "auto";
  setBusy(true);
  const typing = addTyping();

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    sessionId = data.session_id;
    typing.remove();
    if (data.reply) addMessage("agent", data.reply);
    (data.events || []).forEach(addAnnotation);
    if (data.ended) markEnded(data.outcome);
  } catch (err) {
    typing.remove();
    el.status.dataset.state = "down";
    el.status.textContent = "offline";
    addError(`${err.message}. Check the backend is running and the endpoint above is correct.`);
  } finally {
    if (!ended) setBusy(false);
  }
}

function markEnded(outcome) {
  ended = true;
  el.endBtn.disabled = true;
  el.endedBar.hidden = false;
  el.endedOutcome.textContent = outcome || "closed";
  el.input.disabled = true;
  el.send.disabled = true;
  el.status.dataset.state = "idle";
  el.status.textContent = "closed";
}

/* ── The lead record ───────────────────────────────────────────────────── */

const FIELD_GROUPS = [
  ["Lead", "lead", [["name", "Name"], ["phone", "Phone"],
                    ["language_preference", "Language"]]],
  ["Requirement", "requirement", [["configuration_interest", "Config"],
                                  ["budget_stated", "Budget"],
                                  ["budget_fit", "Budget fit"],
                                  ["purpose", "Purpose"],
                                  ["timeline", "Timeline"],
                                  ["funding", "Funding"]]],
  ["Qualification", "qualification", [["interest_level", "Interest"],
                                      ["qualification_score", "Score"],
                                      ["objections_raised", "Objections"],
                                      ["questions_agent_could_not_answer", "Unanswered"]]],
  ["Outcome", "outcome", [["site_visit_status", "Site visit"],
                          ["booking_failure_reason", "Failure"],
                          ["follow_up_required", "Follow up"],
                          ["follow_up_when", "When"],
                          ["do_not_contact", "Do not contact"],
                          ["escalate_to_human", "Escalated"]]],
];

function fmt(value) {
  if (value === null || value === undefined || value === "" ||
      (Array.isArray(value) && value.length === 0)) return null;
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value).replace(/_/g, " ");
}

function renderAnalytics(a) {
  const root = document.createElement("div");
  root.className = "dossier-groups";

  for (const [title, key, fields] of FIELD_GROUPS) {
    const src = a[key] || {};
    const group = document.createElement("section");
    group.className = "dgroup";
    const h = document.createElement("h3");
    h.className = "label";
    h.textContent = title;
    const dl = document.createElement("dl");
    for (const [field, label] of fields) {
      const value = fmt(src[field]);
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value ?? "—";
      if (value === null) dd.className = "null";
      dl.append(dt, dd);
    }
    group.append(h, dl);
    root.append(group);
  }

  const outcome = a.outcome || {};
  let stamp = null;
  if (outcome.site_visit_status === "confirmed") stamp = ["ok", "Site visit booked"];
  else if (outcome.do_not_contact) stamp = ["", "Do not contact"];
  else if (outcome.escalate_to_human) stamp = ["", "Escalated"];
  else if (outcome.follow_up_required) stamp = ["", "Follow up required"];
  if (stamp) {
    const s = document.createElement("div");
    s.className = `stamp ${stamp[0]}`.trim();
    s.textContent = stamp[1];
    root.append(s);
  }

  if (a.summary) {
    const p = document.createElement("p");
    p.className = "summary";
    p.innerHTML = "<b>Summary</b>";
    p.append(document.createTextNode(a.summary));
    root.append(p);
  }
  if (a.next_best_action) {
    const p = document.createElement("p");
    p.className = "summary";
    p.innerHTML = "<b>Next best action</b>";
    p.append(document.createTextNode(a.next_best_action));
    root.append(p);
  }

  const raw = document.createElement("details");
  raw.className = "raw";
  const sum = document.createElement("summary");
  sum.textContent = "Raw JSON";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(a, null, 2);
  raw.append(sum, pre);
  root.append(raw);

  el.analyticsSlot.replaceChildren(root);
}

async function generateAnalytics() {
  if (!sessionId) return;
  el.analyticsBtn.disabled = true;
  el.analyticsBtn.textContent = "Generating…";
  el.analyticsSlot.innerHTML = '<p class="empty">Extracting the lead record from the transcript…</p>';
  try {
    const data = await api("/api/analytics", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
    renderAnalytics(data.analytics || {});
  } catch (err) {
    el.analyticsSlot.innerHTML = '<p class="empty"></p>';
    el.analyticsSlot.querySelector("p").textContent = `Could not generate: ${err.message}`;
  } finally {
    el.analyticsBtn.disabled = false;
    el.analyticsBtn.textContent = "Regenerate lead record";
  }
}

/* ── Seeded hard cases. These are the assignment's difficult situations,
      one click each, so a reviewer can reach them without typing. ───────── */

const PROBES = [
  ["Hinglish · qualify", "Hi, Sector 79 wala project ke bare mein jaanna tha"],
  ["Hindi · price", "नमस्ते, 3 BHK की कीमत क्या है?"],
  ["Objection · discount", "Bhai discount kitna milega? Best price bata do"],
  ["Unknown fact", "What is the carpet area and the possession date?"],
  ["Busy customer", "Abhi main drive kar raha hoon, baad mein baat karte hain"],
  ["Do not contact", "Mujhe interest nahi hai, dobara call mat karna"],
  ["Booking · will fail", "I want a site visit this Saturday at 11 am"],
  ["Ask for a human", "I don't want to talk to a bot, get me a real person"],
];

function renderProbes() {
  el.probes.replaceChildren(...PROBES.map(([tag, text]) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = '<span class="tag"></span><span class="t"></span>';
    b.querySelector(".tag").textContent = tag;
    b.querySelector(".t").textContent = text;
    b.addEventListener("click", () => send(text));
    li.append(b);
    return li;
  }));
}

/* ── Boot ──────────────────────────────────────────────────────────────── */

async function connect() {
  el.apiBase.value = API;
  el.status.dataset.state = "idle";
  el.status.textContent = "connecting";
  try {
    const cfg = await api("/api/config");
    el.model.textContent = cfg.model || "—";
    const p = cfg.project || {};
    const rows = [
      ["Project", p.project],
      ["Location", p.location],
      ["Config", (p.configurations || []).join(" · ")],
      ["2 BHK from", (p.pricing || {})["2 BHK"]],
      ["3 BHK from", (p.pricing || {})["3 BHK"]],
      ["Open", (p.site_visit || {}).days_open],
      ["Slots", ((p.site_visit || {}).slots || []).map((t) => t.replace(":00", "")).join(" · ")],
    ];
    el.spec.replaceChildren(...rows.flatMap(([k, v]) => {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v || "—";
      return [dt, dd];
    }));
    el.status.dataset.state = "ok";
    el.status.textContent = "connected";
  } catch (err) {
    el.status.dataset.state = "down";
    el.status.textContent = "offline";
    addError(`Cannot reach the backend at ${API} — ${err.message}`);
  }
}

function resetConversation() {
  if (sessionId) {
    api("/api/reset", { method: "POST", body: JSON.stringify({ session_id: sessionId }) })
      .catch(() => { /* a stale session is harmless */ });
  }
  sessionId = null;
  ended = false;
  el.log.replaceChildren();
  el.endedBar.hidden = true;
  el.events.replaceChildren(Object.assign(document.createElement("li"), {
    className: "empty",
    textContent: "No tool calls yet. Booking attempts, escalations and the close will be logged here as they happen.",
  }));
  el.analyticsSlot.innerHTML =
    '<p class="empty">Generated after the conversation ends. End the chat, or say goodbye, then generate.</p>';
  el.analyticsBtn.textContent = "Generate lead record";
  el.endBtn.disabled = false;
  el.input.value = "";
  setBusy(false);
  addMessage("agent",
    "Hello! I'm Meera from Northstar Homes. Ask me about Northstar One in Sector 79, Gurugram — in English, हिंदी, or Hinglish.");
}

el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(el.input.value);
});

el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send(el.input.value);
  }
});

el.input.addEventListener("input", () => {
  el.input.style.height = "auto";
  el.input.style.height = `${Math.min(el.input.scrollHeight, 128)}px`;
});

el.resetBtn.addEventListener("click", resetConversation);

// Ending by hand. The agent closes the conversation itself when the customer
// says goodbye, but a reviewer may want the lead record at any point — and a
// scripted demo needs the ending to be deterministic.
el.endBtn.addEventListener("click", () => {
  if (!sessionId) return;
  if (!ended) markEnded("ended_manually");
  generateAnalytics();
});
el.analyticsBtn.addEventListener("click", generateAnalytics);

el.settingsBtn.addEventListener("click", () => {
  const open = el.settings.hidden;
  el.settings.hidden = !open;
  el.settingsBtn.setAttribute("aria-expanded", String(open));
  if (open) el.apiBase.focus();
});

el.settings.addEventListener("submit", (e) => {
  e.preventDefault();
  API = el.apiBase.value.trim().replace(/\/$/, "") || DEFAULT_LOCAL;
  localStorage.setItem("northstar.api", API);
  el.settings.hidden = true;
  el.settingsBtn.setAttribute("aria-expanded", "false");
  resetConversation();
  connect();
});

renderProbes();
resetConversation();
connect();
