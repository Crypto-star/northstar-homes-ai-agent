# Progress Tracker — Huvo AI FDE Assignment

Source of truth: `huvo assignment.pdf`. Every row is lifted from the PDF and
cross-checked against it after implementation.
Status: `[ ]` todo · `[~]` in progress · `[x]` done & verified.

## Hard constraints
| # | Requirement (PDF) | Status | Evidence |
|---|---|---|---|
| C1 | Backend MUST be FastAPI (Python) | [x] | `backend/main.py` — FastAPI, uvicorn. No Express anywhere. |
| C2 | Agent must not invent prices/discounts/availability/any unprovided info | [x] | `PROMPT.md` §2 + §11; scenarios `discount_pressure`, `unknown_questions`, `prompt_injection` all pass |
| C3 | Same prompt usable for chat AND voice | [x] | `PROMPT.md` §4 written TTS-first; `{{CHANNEL}}` injected by `backend/prompt.py` |
| C4 | No API keys/secrets committed | [x] | `.env` gitignored (`git check-ignore` verified); `.env.example` has placeholders only |

## Part 1 — Prompt
| # | Must handle | Status | Where in `PROMPT.md` | Proven by |
|---|---|---|---|---|
| P1.1 | Natural conversation | [x] | §4, §6 | every scenario |
| P1.2 | Customer qualification | [x] | §6 (five slots) | `hinglish_hot_booking`, `memory_and_contradiction` |
| P1.3 | English, Hindi, Hinglish | [x] | §5 | `hinglish_hot_booking`, `budget_below_range` (Devanagari), `do_not_contact` |
| P1.4 | Common objections | [x] | §7 | `discount_pressure`, `budget_below_range` |
| P1.5 | Busy or uninterested customers | [x] | §8 | `busy_callback`, `budget_below_range` |
| P1.6 | Requests to contact later | [x] | §8 | `busy_callback`, `memory_and_contradiction` |
| P1.7 | Requests to stop further communication | [x] | §8 (hard stop, distinct from "later") | `do_not_contact` |
| P1.8 | Unknown questions | [x] | §2 (+ refusal budget) | `unknown_questions` |
| P1.9 | Site-visit booking | [x] | §9 `book_site_visit` | `hinglish_hot_booking` |
| P1.10 | Booking failures | [x] | §9 "When the booking FAILS", 7 reasons | `booking_failure_recovery`, `booking_system_down` |
| P1.11 | Human escalation | [x] | §9 `escalate_to_human` | `discount_pressure`, `angry_human_escalation`, `unknown_questions` |
| P1.12 | Proper conversation ending | [x] | §10 + `end_conversation` | every scenario ends with an `end` event |

## Part 2 — Bot
| # | Requirement | Status | Evidence |
|---|---|---|---|
| P2.1 | Text-based conversational bot | [x] | `POST /api/chat` |
| P2.2 | Simple web interface | [x] | `frontend/` — static HTML/CSS/JS, no build, GitHub Pages ready |
| P2.3 | Accept customer messages | [x] | `ChatRequest` |
| P2.4 | Respond using final prompt | [x] | `backend/prompt.py` reads `PROMPT.md` at runtime — one source of truth |
| P2.5 | Remember info shared during conversation | [x] | full transcript replayed each turn; `memory_and_contradiction` explicitly tests recall of a *changed* budget and the name |
| P2.6 | Support English, Hindi, Hinglish | [x] | see P1.3 |
| P2.7 | Handle different intents and objections | [x] | 11 scenarios covering 11 distinct intents |
| P2.8 | Simulate a site-visit booking | [x] | `backend/booking.py` with slot inventory and booking IDs |
| P2.9 | Handle a failed booking correctly | [x] | 7 failure reasons; `slot_full`, `closed_sunday`, `system_unavailable` all exercised |
| P2.10 | Analytics after conversation ends | [x] | `backend/analytics.py` — budget, budget fit, config, interest level, qualification score, objections, unanswered questions, site-visit status, follow-up, DNC, escalation, summary, next action |
| P2.11 | Test cases: input / expected / actual | [x] | `docs/TEST_CASES.md` — 11 scenarios, full transcripts, **11/11 pass** |

## Beyond the brief
| Item | Why |
|---|---|
| Analytics assertions in the test runner | behaviour regressions fail a field instead of needing a human to notice |
| Tool-XML recovery in `llm.py` | Qwen sometimes emits tool markup as text; unhandled it both leaks into the chat and silently drops the booking |
| Forced spoken turn after a tool chain | model booked, escalated and closed in one turn without speaking — customer would have seen a bare goodbye after a failed booking |
| `prompt_injection` scenario | not required, but a sales agent that can be talked into a fake price is the real risk |

## Project facts (the ONLY facts the agent may state)
- Project: Northstar One · Location: Sector 79, Gurugram
- Configurations: 2 BHK and 3 BHK
- Starting price: 2 BHK ₹1.35 crore onwards · 3 BHK ₹1.75 crore onwards
- (Invented, and flagged as such in the README: site-visit days Mon–Sat and slots 11/1/3/5, because "book a site visit" needs an inventory)

## Submission
| # | Item | Status |
|---|---|---|
| S1 | Public GitHub repo | [ ] awaiting push |
| S2 | Final prompt in repo | [x] `PROMPT.md` |
| S3 | Source code | [x] `backend/`, `frontend/` |
| S4 | README (run, assumptions, limitations, AI tools) | [x] `README.md` |
| S5 | `.env.example` | [x] |
| S6 | Demo video | [~] recorded + narrated, assembling |
| S7 | Email to aditi@huvo.ai, CC nikhil/vaibhav/rohit@huvo.ai | [ ] draft ready in `docs/EMAIL.md` |

## Build log
- Read PDF, confirmed Groq `qwen/qwen3.6-27b` (131k ctx); `reasoning_effort:"none"` suppresses `<think>`.
- Built booking simulator with deterministic failures; self-check passes.
- Prompt v1 → benchmark found: Hinglish answered in English. Fixed with a per-turn language check plus worked examples.
- Benchmark found the agent looping on "shall I book it?" and never calling the tool. Fixed: exactly one read-back, next yes is a tool call.
- Researched production voice-agent prompting (Vapi, Deepgram, OpenAI Realtime, Retell, ElevenLabs). Prompt v2: compressed the 20-item banlist to five categories plus a principle (Vapi names long banlists as an anti-pattern), added the pre-computed price table, refusal budgeting, anti-stall, identity lock, and per-tool `Use when / Do NOT use when`.
- Found Qwen leaking raw `<tool_call>` XML into replies — stripped it and recovered the call so a booking is never silently lost.
- Found the agent chaining book→escalate→end with no spoken turn on the system-down path. Added a forced tools-off reply.
- **Final: 11/11 scenarios pass**, zero leaked tool markup.
