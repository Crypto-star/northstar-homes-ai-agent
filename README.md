# Northstar Homes — AI Sales Agent

Conversational AI sales agent for a fictional Gurugram real-estate project,
**Northstar One**. Speaks English, Hindi and Hinglish, qualifies the lead, books
a site visit, handles booking failures, and produces a structured lead record
when the conversation ends.

Built for the Huvo AI Forward Deployed Engineer assignment.

- **The prompt** — [`PROMPT.md`](PROMPT.md) (the actual deliverable)
- **Why it is written that way** — [`docs/PROMPT_APPROACH.md`](docs/PROMPT_APPROACH.md)
- **Test cases, with real transcripts** — [`docs/TEST_CASES.md`](docs/TEST_CASES.md)
- **Requirement-by-requirement checklist against the brief** — [`PROGRESS.md`](PROGRESS.md)

| | |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| Model | `qwen/qwen3.6-27b` on Groq |
| Frontend | Static HTML, CSS and JS — no build step, hosts on GitHub Pages |
| Memory | In-process session store (full transcript replayed to the model) |

---

## Run it

```bash
git clone <this-repo> && cd <this-repo>

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then put your Groq key in it

cd backend && uvicorn main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** — the backend serves the UI from the same origin,
so that one command runs the whole thing.

Get a free Groq key at [console.groq.com/keys](https://console.groq.com/keys).

### Hosting the UI on GitHub Pages

`frontend/` is fully static. Publish that folder with Pages, deploy the backend
anywhere (Render, Railway, Fly, a VM), and point the page at it either through
the **Endpoint** button in the header or with a query parameter:

```
https://<user>.github.io/<repo>/?api=https://your-backend.example.com
```

The value is saved to `localStorage`. Set `CORS_ORIGINS` in `.env` to your Pages
origin rather than leaving it as `*`.

---

## What it does

**Qualifies.** Works five slots — configuration, budget, purpose, timeline,
contact — conversationally rather than as a form, and never re-asks something
already answered.

**Speaks three languages.** Mirrors the customer every turn, including script:
roman-script Hindi gets a roman-script reply, Devanagari gets Devanagari.

**Refuses to invent.** The knowledge base is four facts. Everything else —
carpet area, possession, RERA, amenities, discounts, availability — gets an
honest "I don't have that" plus a real next step. Under repeated pressure it
escalates rather than softening.

**Books, and fails safely.** `book_site_visit` can return `slot_full`,
`closed_sunday`, `invalid_slot`, `past_date`, `invalid_phone`,
`unparseable_date` or `system_unavailable`. Each maps to a human explanation
plus a recovery offer in the same reply. It never announces a booking the tool
did not confirm.

**Ends properly.** Do-not-contact is honoured immediately and is kept distinct
from "call me later". Busy customers are let go in one line.

**Produces analytics.** A second LLM pass over the finished transcript emits one
CRM-shaped record: budget, budget fit, configuration, purpose, timeline,
interest level, a 0–100 qualification score, objections raised, questions the
agent could not answer, site-visit status, follow-up requirement, do-not-contact
and escalation flags, a summary and a next best action.

### Three tools, and why they exist

| Tool | Maps to |
|---|---|
| `book_site_visit` | "Simulate a site-visit booking" / "handle a failed booking correctly" |
| `escalate_to_human` | "Human escalation" |
| `end_conversation` | "Proper conversation ending" — and it is what triggers analytics |

Making these tools rather than prose means every one of those behaviours is
observable in the UI and assertable in a test.

---

## Layout

```
PROMPT.md            the system prompt — single source of truth, read at runtime
backend/
  main.py            FastAPI app, session store, tool-call loop
  prompt.py          loads PROMPT.md, injects today's date and the channel
  config.py          env config + the knowledge base
  booking.py         simulated booking with deterministic failures
  analytics.py       post-conversation extraction pass
  llm.py             Groq client: retries, reasoning strip, tool-XML recovery
  tests/
    scenarios.py     11 benchmark conversations
    runner.py        plays them, prints input / expected / actual
frontend/            index.html, style.css, app.js — static, no build
docs/                prompt approach, test-case results
demo/
  drive.mjs          headless-browser driver: plays the demo, records 1080p
  narration.json     the voiceover script, one entry per beat
  voiceover.py       ElevenLabs TTS with word-level timestamps
  assemble.py        slices, freeze-pads, muxes, burns captions
```

## API

| | | |
|---|---|---|
| `POST` | `/api/chat` | `{message, session_id?}` → `{reply, session_id, ended, events, outcome}` |
| `POST` | `/api/analytics` | `{session_id}` → the lead record |
| `POST` | `/api/reset` | clear a session |
| `GET` | `/api/session/{id}` | raw transcript and events |
| `GET` | `/api/config` | project facts and model name |
| `GET` | `/api/health` | liveness |

---

## Tests

```bash
python backend/booking.py                    # booking logic self-check
python backend/tests/runner.py               # all scenarios, live model
python backend/tests/runner.py --md          # markdown, as in docs/TEST_CASES.md
python backend/tests/runner.py discount_pressure

# the booking-system-down path needs the failure flag
FORCE_BOOKING_FAILURE=1 python backend/tests/runner.py booking_system_down
```

Scenarios run the app in-process, so no server needs to be up. Add
`--base http://127.0.0.1:8000` to drive a running one instead.

Each scenario asserts on the generated analytics, so a regression in agent
behaviour shows up as a failed field rather than something a human has to spot.
They call the real model, so expect a few minutes and mild non-determinism in
wording — the assertions are on behaviour, not on exact strings.

Results, with full transcripts: [`docs/TEST_CASES.md`](docs/TEST_CASES.md).

---

## Assumptions

1. **Only the four facts in the brief are known.** Project, location,
   configurations, and the two starting prices. Site-visit days and slots
   (Mon–Sat; 11, 1, 3, 5) are invented, because "book a site visit" is
   meaningless without an inventory to book against. Everything else is treated
   as unknown on purpose — that is the behaviour under test.
2. **The booking system is simulated.** It fails deterministically so the
   failure path is reproducible: this Saturday's 11:00 AM slot is pre-booked,
   Sundays are closed, and `FORCE_BOOKING_FAILURE=1` takes the whole system down.
3. **Analytics run after the conversation, not during.** Asking the sales agent
   to also emit a schema mid-call makes it worse at both jobs.
4. **Chat is the demonstrated channel.** The prompt is written to be
   TTS-safe and takes a `{{CHANNEL}}` value, but no telephony is wired up.
5. **One agent persona, "Meera".** Named so the read-back and closing lines sound
   like a person rather than a system.

## Known limitations

- **Sessions are in memory.** A restart loses every conversation, and it will not
  survive more than one server process. Real deployment wants Redis or Postgres
  behind the same `Session` interface — the store is the only thing that changes.
- **No streaming.** Replies arrive whole, so a long turn shows a typing indicator
  for a second or two.
- **The prompt is ~5.6k tokens.** Fine for chat; on a live call I would split it
  per stage, as Retell and Pipecat do, to cut latency.
- **`reasoning_effort` is `none`.** Qwen3.6's thinking blocks are disabled for
  speed. Hard multi-constraint turns would likely be a little sharper with them on.
- **Date parsing is regex, not NLP.** It handles today/aaj, kal, parso, weekday
  names in English and roman Hindi, ISO dates, and "12 September". Anything odder
  comes back as `unparseable_date` and the agent asks again — which is the right
  failure, but it is a narrow parser.
- **No authentication or rate limiting.** It is a demo; do not put it on the
  public internet with a real key.
- **The model is non-deterministic.** Roughly one run in ten, phrasing drifts —
  for example ending in English after a Hinglish conversation. The scenario suite
  is how that gets caught.

## AI tools used

- **Claude Code** (Opus 5) — wrote the code, the prompt, and this README, and ran
  the benchmark loop. Every behavioural fix in `PROMPT.md` came from a scenario
  failing first: the confirmation loop, the language drift, and the silent
  tool-chain on the booking-failure path were all found this way, not guessed at.
- **Groq** — inference for `qwen/qwen3.6-27b`, both the agent and the analytics pass.
- **ElevenLabs** — voiceover for the demo video.
- **Playwright** — headless browser used to drive and record the demo.

Research into production voice-agent prompting (Vapi, Deepgram, OpenAI Realtime,
Retell, ElevenLabs) is credited in
[`docs/PROMPT_APPROACH.md`](docs/PROMPT_APPROACH.md).
