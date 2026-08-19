# How the prompt was built

The prompt is the deliverable; the bot is the harness that proves it works. This
is the reasoning behind [`../PROMPT.md`](../PROMPT.md).

## Where the structure comes from

I read the published prompting guides for the platforms that actually run
production voice agents, and took the parts that four or more of them agree on:

| Source | What I took |
|---|---|
| [Vapi prompting guide](https://docs.vapi.ai/prompting-guide) | Six-section skeleton; the identity lock; spoken-form number table; the warning against long "never say X" banlists |
| [Deepgram voice-agent prompting](https://developers.deepgram.com/docs/prompting-voice-agents) | "What does a successful call look like" in the identity; the TTS-safety preamble; the anti-stall rule; defining out-of-scope explicitly |
| [OpenAI Realtime prompting guide](https://developers.openai.com/cookbook/examples/realtime_prompting_guide) | `Use when / Do NOT use when` per tool; escalation thresholds written as words, not digits; the "vary your responses" rule; unclear-audio handling |
| [Retell prompt engineering](https://docs.retellai.com/build/prompt-engineering-guide) | A first-class objection-handling section; one question per turn; dates in spoken form |
| [ElevenLabs prompting + guardrails](https://elevenlabs.io/docs/agents-platform/best-practices/prompting-guide) | Guardrails as their own headed section; the tool-error ladder; keeping the prompt lean |
| [Anthropic: reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) | Grounding every claim in a quotable source, which became "only section 3 is true" |

A note on provenance: the research also surfaced another candidate's public
solution to this same assignment. I did not read techniques out of it or copy any
of its text. Everything here traces to the vendor documentation above.

## The decisions that actually mattered

**One prompt, two channels.** The prompt is written so that a text-to-speech
engine could read any reply aloud verbatim. That single constraint produces the
no-markdown, one-question, three-sentence, spoken-numbers rules — and those make
it better in chat too. The only genuine branch is `{{CHANNEL}}`, injected at
runtime, which is why the same file serves both.

**Facts live in exactly one place.** Section 3 is the whole knowledge base, and
section 2 says everything not in it is unknown. `backend/config.py` holds the same
facts and `/api/config` feeds the UI from there, so the prompt, the server, and
the interface cannot drift apart.

**A short principle beat a long banlist.** My first draft listed about twenty
forbidden statements. Vapi's guide argues that every banned phrase is an
activated token that can get over-sampled under uncertainty, so a verbose ban
reads as a menu. I compressed it to five categories plus a principle, and added
the three specific failure modes that a category list does not catch:

- *softening* — "roughly", "typically", "I think" are inventions wearing a hedge
- *confirming by mention* — "you'll see the clubhouse on your visit" invents a
  clubhouse just as surely as stating it does
- *inventing the carrier* — never offer a brochure or floor plan, because you do
  not know one exists

**Refusal budgeting.** Honest agents fail a different way: they answer "I don't
have that, shall I have someone call you?" five times and the conversation dies.
So the prompt counts unknowns — never offer the same next step twice in a row,
and after three consecutive unknowns, escalate to a human instead of deflecting
again.

**Prices are pre-computed, not derived.** The model is given the exact spoken
form in all three languages rather than converting crore-and-lakh figures itself.
That is where numbers get misstated — and "pachhattar" (seventy-five) versus
"sattar" (seventy) is a real, expensive mistake.

**Script wins over language.** For chat specifically: if someone writes Hindi in
roman letters, reply in roman letters. Look at the characters on screen, not at
which language the words belong to. The first version of this prompt said "mirror
the customer" and the model answered Hinglish in English — the fix was an
explicit pre-reply check plus worked examples.

**Booking confirmation is exactly one read-back.** The first version said "read
the details back and get a yes", and the agent looped: read back, customer says
yes, read back again. It never called the tool. The fix is explicit — one
read-back, and the next "haan" is a tool call, not another question. Qualification
answers get no read-back at all, because reading those back turns a conversation
into a form.

## What the failure paths look like

The booking tool returns a machine-readable `reason`, and the prompt maps each
one to a human sentence plus a recovery move in the same reply. `system_unavailable`
is deliberately different from the others: when the booking system is down the
agent cannot see availability at all, so it must not offer alternative times —
it takes the preference by hand and escalates.

Two failed attempts on one booking stops the tool calls entirely and hands over
to a human. Never loop on a failing tool.

## What I would add with more time

- A separate lighter prompt for voice, since ~5.6k tokens costs latency that
  matters on a call more than it does in chat.
- Per-stage prompt swapping (Retell and Pipecat both do this) instead of one
  monolith, once the flow grows past its current five slots.
- Consent and recording disclosure, and DND-registry scrubbing before dialling.
  Both are compliance requirements for real outbound calling in India and neither
  is a prompt-layer problem.
