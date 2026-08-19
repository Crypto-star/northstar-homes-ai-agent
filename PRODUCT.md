# PRODUCT.md — Northstar Homes AI Sales Agent

## Register

product

## Product purpose

A working demo of an AI sales agent for a fictional Gurugram real-estate project,
Northstar One. The interface exists so a person can talk to the agent, watch the
agent's machinery while it works, and read the structured lead record the
conversation produced.

The interface is not the product. The prompt is. The UI's job is to make the
prompt's behaviour legible: which language it mirrored, which facts it refused to
invent, when it called a tool, when a booking failed, and what the CRM ends up
with. A plain chat window hides all of that.

## Users

1. **The evaluator.** Opens the link, has a few minutes, needs to judge whether
   the agent handles a Hinglish objection, a discount push, and a failed booking
   without inventing facts. Needs to see the agent's reasoning surface — tool
   calls, booking failures, the final lead record — not just chat bubbles.
2. **Sales ops at a developer.** Would use this to sanity-check what the bot is
   telling real customers and what lands in the CRM.

Both users care about the same thing: evidence. Not vibes.

## Brand and tone

Northstar Homes is a mid-market Gurugram developer, not a luxury brand. The
product voice is precise, plain, and unembellished. It states starting prices and
refuses to guess. That restraint is the brand.

The interface should feel like a working instrument — a drawing office spec
sheet, an annotated document — rather than a consumer chat app or a glossy
property portal.

## Anti-references

- Glossy property-portal aesthetics: hero renders, gold serif, "luxury living",
  navy-and-gold corporate palette. Northstar is not selling a fantasy.
- The ChatGPT clone: centred column, grey and white bubbles, no context, no
  visible machinery.
- Proptech SaaS blue: white background, blue accent, rounded cards in a grid.
- Editorial warm-cream-plus-serif. Currently everywhere, says nothing about
  real estate.
- Any layout where the analytics output is hidden behind a tab nobody clicks.

## Strategic principles

1. **Show the machinery.** Tool calls, booking failures, and escalations are
   first-class UI, not debug output. The failure path is a feature here.
2. **The lead record is the payoff.** The conversation is the input; the
   structured dossier is the deliverable. Give it real space.
3. **Multilingual is a demo requirement, so make it one click.** Seeded openers
   in English, Hindi, and Hinglish, plus the hard cases (discount pressure,
   do-not-contact) that prove the prompt works.
4. **Static and portable.** The frontend is plain HTML, CSS, and JS with no build
   step and no framework, and it can point at any backend URL.
5. **Every fact on screen comes from the backend.** The UI never hardcodes a
   price. It reads `/api/config`. A demo that can drift from the knowledge base
   defeats the point of the prompt.
