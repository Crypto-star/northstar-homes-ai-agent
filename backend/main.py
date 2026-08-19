"""FastAPI backend for the Northstar Homes AI sales agent.

Endpoints
  GET  /api/health     liveness + which model is wired up
  GET  /api/config     project facts, so the UI never hardcodes a price
  POST /api/chat       one customer turn in, one agent turn out
  POST /api/analytics  post-conversation structured lead record
  POST /api/reset      clear a session
  GET  /api/session/{id}  raw transcript + captured events (debug / demo)

Memory: an in-process dict of session_id -> Session. The full message history is
what gives the agent its memory, so "remember what I said earlier" is handled by
replaying the transcript, not by a side database. See README for the trade-off.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import analytics
from booking import book_site_visit
from config import CORS_ORIGINS, KNOWLEDGE_BASE, MAX_HISTORY_TURNS, MODEL, ROOT
from llm import LLMError, chat
from prompt import build_system_prompt

app = FastAPI(title="Northstar Homes AI Sales Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Tools. Each one exists because the assignment names it as a behaviour to
# handle: booking, booking failure, human escalation, and ending the call.
# Types are unions with null because Qwen occasionally emits a phone number as a
# JSON number, and Groq rejects the call at schema-validation time if we don't.
# --------------------------------------------------------------------------- #
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "book_site_visit",
            "description": (
                "Book a site visit at Northstar One. Call ONLY after you have "
                "explicitly collected the customer's name, 10-digit mobile number, "
                "a date and a time slot, and they have confirmed them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"], "description": "Customer's full name"},
                    "phone": {"type": ["string", "number", "null"],
                              "description": "10-digit Indian mobile number"},
                    "date": {"type": ["string", "null"],
                             "description": "Date as the customer said it, e.g. 'saturday', "
                                            "'kal', '2026-08-22'"},
                    "time_slot": {"type": ["string", "null"],
                                  "description": "Requested time, e.g. '11am', '3 PM'"},
                },
                "required": ["name", "phone", "date", "time_slot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Hand the conversation to a human sales manager. Call when the "
                "customer asks for a human, is angry, or needs something you are "
                "not allowed to decide (discounts, negotiation, legal, payment plans)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": ["string", "null"]},
                    "customer_phone": {"type": ["string", "number", "null"]},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_conversation",
            "description": (
                "Close the conversation after you have said your goodbye. Call when "
                "the customer says bye/thanks-that's-all, asks not to be contacted "
                "again, or the visit is booked and there is nothing left to do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "outcome": {
                        "type": ["string", "null"],
                        "description": "one of: site_visit_booked, follow_up_scheduled, "
                                       "not_interested, do_not_contact, escalated, "
                                       "information_only",
                    },
                    "do_not_contact": {"type": ["boolean", "null"]},
                    "follow_up_when": {"type": ["string", "null"]},
                },
                "required": ["outcome"],
            },
        },
    },
]


@dataclass
class Session:
    id: str
    messages: list[dict] = field(default_factory=list)
    booking_ids: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    ended: bool = False
    outcome: str | None = None
    do_not_contact: bool = False
    escalated: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    _analytics: dict | None = None


SESSIONS: dict[str, Session] = {}


def get_session(session_id: str | None) -> Session:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    sid = session_id or uuid.uuid4().hex[:12]
    SESSIONS[sid] = Session(id=sid)
    return SESSIONS[sid]


def _window(messages: list[dict]) -> list[dict]:
    """Trim to the last N turns without orphaning a tool result from its call."""
    limit = MAX_HISTORY_TURNS * 2
    if len(messages) <= limit:
        return messages
    trimmed = messages[-limit:]
    while trimmed and trimmed[0].get("role") in ("tool", "assistant"):
        trimmed = trimmed[1:]
    return trimmed


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    ended: bool
    events: list[dict]
    outcome: str | None = None


def _run_tool(name: str, args: dict, session: Session) -> dict:
    """Execute a tool call and record what happened on the session."""
    if name == "book_site_visit":
        result = book_site_visit(
            str(args.get("name") or ""),
            str(args.get("phone") or ""),
            str(args.get("date") or ""),
            str(args.get("time_slot") or ""),
        )
        if result["status"] == "confirmed":
            session.booking_ids.append(result["booking_id"])
        session.events.append({"type": "booking", "result": result})
        return result

    if name == "escalate_to_human":
        session.escalated = True
        result = {
            "status": "escalated",
            "ticket_id": f"ESC-{uuid.uuid4().hex[:5].upper()}",
            "message": "A human sales manager has been notified and will call back.",
            "reason": args.get("reason"),
        }
        session.events.append({"type": "escalation", "result": result})
        return result

    if name == "end_conversation":
        if session.ended:
            # Model sometimes fires the closer twice; the first one is the truth.
            return {"status": "already_ended", "outcome": session.outcome}
        session.ended = True
        session.outcome = args.get("outcome") or "information_only"
        session.do_not_contact = bool(args.get("do_not_contact"))
        result = {"status": "ended", "outcome": session.outcome}
        session.events.append({"type": "end", "result": {**result, **args}})
        return result

    return {"status": "error", "message": f"Unknown tool {name}"}


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest) -> ChatResponse:
    session = get_session(req.session_id)
    turn_start = len(session.events)
    session.messages.append({"role": "user", "content": req.message})

    system = {"role": "system", "content": build_system_prompt()}
    reply = ""

    # At most three tool rounds per turn: e.g. booking fails -> retry -> end.
    for _ in range(3):
        try:
            msg = chat(
                [system, *_window(session.messages)],
                tools=TOOLS,
            )
        except LLMError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        tool_calls = msg.get("tool_calls") or []
        session.messages.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            **({"tool_calls": tool_calls} if tool_calls else {}),
        })

        if not tool_calls:
            reply = msg.get("content") or ""
            break

        for call in tool_calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(fn["name"], args, session)
            session.messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    if not reply:
        # The model chained tool calls and never spoke — most often on the
        # booking-failed path, where it books, escalates and closes in one turn.
        # An empty bubble there would leave the customer thinking the visit was
        # booked, so ask once more with the tools removed: it can only talk now,
        # and it has every tool result in context to talk about.
        try:
            forced = chat([system, *_window(session.messages), {
                "role": "system",
                "content": "Reply to the customer now, in words, in their language. "
                           "Tell them plainly what just happened and what happens next. "
                           "Do not call any tool.",
            }])
            reply = (forced.get("content") or "").strip()
            if reply:
                session.messages.append({"role": "assistant", "content": reply})
        except LLMError:
            reply = ""

    if not reply:
        reply = ("Thank you for your time. Have a good day!" if session.ended
                 else "Sorry, could you please repeat that?")
        session.messages.append({"role": "assistant", "content": reply})

    return ChatResponse(
        session_id=session.id,
        reply=reply,
        ended=session.ended,
        events=session.events[turn_start:],
        outcome=session.outcome,
    )


class SessionRequest(BaseModel):
    session_id: str


@app.post("/api/analytics")
def api_analytics(req: SessionRequest) -> dict:
    session = SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    if session._analytics is None:
        try:
            session._analytics = analytics.generate(session.messages, session.booking_ids)
        except LLMError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "session_id": session.id,
        "started_at": session.created_at,
        "turns": sum(1 for m in session.messages if m["role"] == "user"),
        "ended": session.ended,
        "analytics": session._analytics,
    }


@app.post("/api/reset")
def api_reset(req: SessionRequest) -> dict:
    SESSIONS.pop(req.session_id, None)
    return {"status": "reset"}


@app.get("/api/session/{session_id}")
def api_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return {"session_id": session.id, "messages": session.messages,
            "events": session.events, "ended": session.ended}


@app.get("/api/config")
def api_config() -> dict:
    return {"project": KNOWLEDGE_BASE, "model": MODEL}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "model": MODEL, "active_sessions": len(SESSIONS)}


# Serve the static UI from the same origin so `uvicorn` alone runs the whole demo.
# Mounted last, at the root, so every /api route above still wins. html=True makes
# "/" resolve to index.html while keeping the relative style.css / app.js paths
# working.
FRONTEND = ROOT / "frontend"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
