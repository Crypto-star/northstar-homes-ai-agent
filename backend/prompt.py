"""Loads the system prompt from the repo-root PROMPT.md.

PROMPT.md is the deliverable a reviewer opens first, so it is the single source
of truth rather than a Python string literal that drifts away from it. Only the
fenced ```text block is sent to the model; the surrounding explanation is not.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from config import ROOT

PROMPT_FILE = ROOT / "PROMPT.md"
_FENCE = re.compile(r"```text\n(.*?)\n```", re.DOTALL)


def _template() -> str:
    raw = PROMPT_FILE.read_text(encoding="utf-8")
    match = _FENCE.search(raw)
    if not match:
        raise RuntimeError(f"{PROMPT_FILE} is missing its ```text prompt block")
    return match.group(1)


def build_system_prompt(channel: str = "chat", today: date | None = None) -> str:
    """Render the prompt for a channel. `channel` is "chat" or "voice"."""
    today = today or date.today()
    return (
        _template()
        .replace("{{TODAY}}", today.isoformat())
        .replace("{{DAY_NAME}}", today.strftime("%A"))
        .replace("{{TOMORROW}}", (today + timedelta(days=1)).strftime("%A, %Y-%m-%d"))
        .replace("{{CHANNEL}}", channel)
    )


if __name__ == "__main__":
    text = build_system_prompt()
    assert "{{" not in text, "unsubstituted placeholder left in prompt"
    assert "Northstar One" in text and "1.35 crore" in text
    print(text)
    print(f"\n--- {len(text)} chars, ~{len(text) // 4} tokens ---")
