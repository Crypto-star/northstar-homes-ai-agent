"""Thin Groq (OpenAI-compatible) chat client.

Deliberately not the openai SDK: one httpx POST is the whole integration, and it
keeps the dependency list short enough to read.
"""

from __future__ import annotations

import json
import time
import re

import httpx

from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    MAX_TOKENS,
    MODEL,
    REASONING_EFFORT,
    TEMPERATURE,
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

# Qwen sometimes emits its native tool-call markup as plain text instead of a
# parsed tool_calls entry — usually when it speaks and calls a tool in the same
# message. Left alone, the XML shows up in the customer's chat bubble AND the
# action silently never happens, which on the booking path means telling someone
# their visit is confirmed when nothing was booked. So we strip it from the
# visible text and re-materialise it as a real tool call.
_TOOL_XML = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.DOTALL)
_FN_XML = re.compile(r"<function=([a-z_]+)>\s*(.*?)\s*(?:</function>|$)", re.DOTALL)
_PARAM_XML = re.compile(r"<parameter=([a-z_]+)>\s*(.*?)\s*(?:</parameter>|$)", re.DOTALL)


def _recover_inline_tool_calls(content: str) -> tuple[str, list[dict]]:
    """Return (cleaned_text, recovered_tool_calls) for leaked Qwen tool markup."""
    recovered: list[dict] = []
    for block in _TOOL_XML.findall(content):
        for idx, (fn_name, body) in enumerate(_FN_XML.findall(block)):
            args = {k: v.strip() for k, v in _PARAM_XML.findall(body)}
            recovered.append({
                "id": f"recovered_{fn_name}_{idx}",
                "type": "function",
                "function": {"name": fn_name, "arguments": json.dumps(args)},
            })
    cleaned = _TOOL_XML.sub("", content).strip()
    return cleaned, recovered


class LLMError(RuntimeError):
    pass


def _post_with_retries(payload: dict, timeout: float, attempts: int = 4) -> dict:
    """POST to the provider, retrying the failures that are actually transient.

    Two provider quirks matter here and both are worth handling rather than
    surfacing to a customer mid-conversation:

      429 / 5xx        rate limit or a blip -> exponential backoff and retry.
      tool_use_failed  Qwen sometimes emits a tool call whose argument types do
                       not match the schema (a phone number as a JSON number,
                       say) and Groq rejects it at validation time. Retrying
                       usually resamples a valid call; if it keeps failing we
                       drop the tools for a final attempt so the agent at least
                       replies with words instead of the turn 502-ing.
    """
    last = ""
    for attempt in range(attempts):
        try:
            r = httpx.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json=payload,
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            last = f"transport error: {e}"
            time.sleep(0.6 * 2**attempt)
            continue

        if r.status_code == 200:
            return r.json()["choices"][0]["message"]

        last = f"{r.status_code}: {r.text[:300]}"
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("retry-after") or 0.6 * 2**attempt))
            continue
        if r.status_code == 400 and "tool_use_failed" in r.text:
            if attempt >= attempts - 2 and "tools" in payload:
                payload = {k: v for k, v in payload.items()
                           if k not in ("tools", "tool_choice")}
            time.sleep(0.3)
            continue
        break

    raise LLMError(f"Model provider request failed after {attempts} attempts — {last}")


def chat(
    messages: list[dict],
    *,
    model: str = MODEL,
    tools: list[dict] | None = None,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
    response_format: dict | None = None,
    timeout: float = 60.0,
) -> dict:
    """Return the assistant message dict: {"content": str|None, "tool_calls": [...]}."""
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set. Copy .env.example to .env and fill it in.")

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": REASONING_EFFORT,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if response_format:
        payload["response_format"] = response_format

    msg = _post_with_retries(payload, timeout)
    if msg.get("content"):
        # Belt-and-braces: strip reasoning even though reasoning_effort is "none".
        text = _THINK.sub("", msg["content"]).strip()
        text, recovered = _recover_inline_tool_calls(text)
        msg["content"] = text
        if recovered and not msg.get("tool_calls"):
            msg["tool_calls"] = recovered
    return msg


def chat_json(messages: list[dict], *, model: str = MODEL, max_tokens: int = 1200) -> dict:
    """Ask for JSON and parse it, tolerating a stray ```json fence."""
    msg = chat(
        messages,
        model=model,
        temperature=0.1,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    raw = (msg.get("content") or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"Model did not return valid JSON: {raw[:300]}") from e
