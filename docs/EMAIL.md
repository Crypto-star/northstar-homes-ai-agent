# Submission email (draft)

**To:** aditi@huvo.ai
**CC:** nikhil@huvo.ai, vaibhav@huvo.ai, rohit@huvo.ai
**Subject:** Forward Deployed Engineer assignment — Northstar Homes AI sales agent

---

Hi Aditi,

Here is my submission for the Forward Deployed Engineer assignment.

**Repository:** https://github.com/Crypto-star/northstar-homes-ai-agent
**Demo video:** <VIDEO_URL>

A few notes that may save you time:

- **The prompt is `PROMPT.md` at the repo root.** It is the actual file loaded at
  runtime, not a copy, so what you read is exactly what the model receives.
  `docs/PROMPT_APPROACH.md` explains why each section is written the way it is,
  and credits the production voice-agent guides the structure draws on.
- **`docs/TEST_CASES.md` has 11 scripted scenarios** with input, expected
  behaviour and actual output for every turn, plus the analytics record each one
  produced. All 11 pass. They cover discount pressure, five unanswerable
  questions in a row, a do-not-contact request, a Devanagari lead below budget, a
  prompt-injection attempt, a booking that fails on a full slot and recovers, and
  a booking system that is completely down.
- **`PROGRESS.md` maps every line of the brief to where it is implemented and
  which scenario proves it**, if you would rather check against the spec directly.

Three things I would call out:

1. The interesting failure mode with an honest agent is not hallucination, it is
   refusal fatigue — answering "I don't have that, shall I have someone call
   you?" five times until the conversation dies. The prompt counts unknowns and
   escalates to a human after three rather than deflecting again.
2. Booking, escalation and ending are real tool calls rather than prose, so each
   is visible in the UI and assertable in a test. The booking system distinguishes
   seven failure reasons, and "system down" is deliberately handled differently
   from "slot taken": when the agent cannot see availability at all, it must not
   offer alternative times.
3. Every behavioural fix in the prompt came from a scenario failing first — the
   confirmation loop, the Hinglish-answered-in-English drift, and a silent
   tool-chain that would have shown a customer a bare goodbye after a failed
   booking. The build log at the bottom of `PROGRESS.md` has the sequence.

The frontend is plain HTML, CSS and JS with no build step, and the backend serves
it, so the README's one command runs the whole thing.

Happy to walk through any of it.

Best,
Hardik
