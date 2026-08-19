# DESIGN.md — Northstar One agent console

## Direction: "Spec sheet"

The interface is an annotated drawing-office document, not a chat app. Real
estate is drawings, dimensions, and marked-up revisions long before it is a
glossy render, and that vocabulary is the one thing this product can borrow that
its anti-references cannot.

Concretely: hairline rules instead of card borders, uppercase mono field labels
like a title block, a faint graph-paper ground, and every automated action
rendered as a red-pencil annotation the way a checker marks up a print.

The memorable element is the right-hand **lead dossier** — a title block that
fills in as the conversation runs, then stamps itself when the call ends.

## Scene sentence

An evaluator on a 15-inch laptop, indoors under office light on a weekday
afternoon, with four minutes to decide whether this agent hallucinates a price.
Bright room, short attention, needs to read fine print. That forces **light**.

A dark variant ships for `prefers-color-scheme: dark` — the same drawing
inverted into a blueprint, which is the one place dark mode is literally
period-correct.

## Color

Strategy: **restrained**, one accent under 10 percent. The document is the
subject; the annotation is the accent. OKLCH throughout, no `#000`, no `#fff`,
every neutral tinted toward the ink hue.

| Token | Light | Role |
|---|---|---|
| `--paper` | `oklch(0.977 0.004 85)` | warm drafting-paper ground |
| `--paper-2` | `oklch(0.945 0.006 85)` | recessed panels, agent bubbles |
| `--ink` | `oklch(0.24 0.021 250)` | primary text, blue-black drafting ink |
| `--ink-2` | `oklch(0.50 0.016 250)` | secondary text, labels |
| `--ink-3` | `oklch(0.68 0.012 250)` | hairlines, grid |
| `--redline` | `oklch(0.55 0.19 28)` | the accent: tool calls, failures, stamps |
| `--sign` | `oklch(0.52 0.12 155)` | confirmations only |

Dark inverts to a blueprint: `--paper: oklch(0.22 0.03 250)`, cyan grid,
`--redline` lifted to `oklch(0.68 0.17 28)` so it survives the dark ground.

Redline is the only saturated colour and appears on maybe six elements. Green is
reserved exclusively for a confirmed booking, so it means something when it shows.

## Typography

- **Archivo** (variable, `wdth` axis) — UI and conversation. Expanded and tight-
  tracked for the masthead, normal width for body. Characterful grotesque,
  drafting-adjacent, not Inter.
- **DM Mono** — field labels, event log, booking references, JSON. Everything a
  title block would set in a technical hand.

Scale ratio 1.3. Labels are 11px mono, uppercase, `letter-spacing: 0.14em`.
Conversation text is 15px, line length capped at 62ch.

## Layout

Three columns on desktop, no wrapper container, no card grid:

```
┌────────────┬──────────────────────────┬──────────────┐
│ SPEC       │ CONVERSATION             │ DOSSIER      │
│ (project   │ (the transcript, the     │ (events live,│
│  facts +   │  only scrolling region)  │  analytics   │
│  scenarios)│                          │  on end)     │
└────────────┴──────────────────────────┴──────────────┘
```

Columns are divided by 1px hairlines, not gaps and shadows. Under 1000px the
dossier collapses to a sheet below the conversation; under 720px the spec rail
collapses into a summary strip.

## Motion

Message entry: 260ms `cubic-bezier(0.16, 1, 0.3, 1)`, 6px rise, opacity only —
no layout properties animated. The typing indicator is three ruled ticks, not
bouncing dots. The confirmation stamp rotates in once at `-3deg`. Everything
respects `prefers-reduced-motion`.

## Bans observed

No side-stripe accents, no gradient text, no glassmorphism, no hero metric, no
identical card grid, no modals. The dossier is inline, always visible, never a
dialog.
