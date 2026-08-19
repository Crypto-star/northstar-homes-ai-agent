"""Post-conversation analytics: a second LLM pass that turns the transcript into
one structured lead record a CRM could ingest.

Separated from the sales prompt on purpose. Asking the sales agent to also emit
analytics mid-call makes it leak schema language into what it says to the
customer, and makes it worse at both jobs. Extraction runs once, after the call.
"""

from __future__ import annotations

from datetime import date

from booking import BOOKINGS
from config import ANALYTICS_MODEL
from llm import chat_json

ANALYTICS_SCHEMA_HINT = """{
  "lead": {
    "name": string|null,
    "phone": string|null,
    "language_preference": "english"|"hindi"|"hinglish"|"unknown"
  },
  "requirement": {
    "configuration_interest": ["2 BHK"|"3 BHK"]|[],
    "budget_stated": string|null,
    "budget_min_inr": number|null,
    "budget_max_inr": number|null,
    "budget_fit": "within_range"|"below_range"|"above_range"|"unknown",
    "purpose": "end_use"|"investment"|"unknown",
    "timeline": "immediate"|"1_3_months"|"3_6_months"|"6_plus_months"|"unknown",
    "funding": "loan"|"self_funded"|"mixed"|"unknown",
    "current_location": string|null
  },
  "qualification": {
    "interest_level": "hot"|"warm"|"cold"|"not_interested",
    "qualification_score": number,
    "score_rationale": string,
    "objections_raised": [string],
    "questions_agent_could_not_answer": [string]
  },
  "outcome": {
    "site_visit_status": "confirmed"|"attempted_failed"|"proposed_not_confirmed"|"declined"|"not_discussed",
    "site_visit": {"booking_id": string|null, "date": string|null, "time_slot": string|null},
    "booking_failure_reason": string|null,
    "follow_up_required": boolean,
    "follow_up_when": string|null,
    "do_not_contact": boolean,
    "escalate_to_human": boolean,
    "escalation_reason": string|null,
    "conversation_ended_by": "customer"|"agent"|"incomplete"
  },
  "summary": string,
  "next_best_action": string
}"""

EXTRACTOR_PROMPT = """You are a CRM data extraction engine for Northstar Homes.

You will be given the full transcript of a sales conversation between an AI agent
and a prospective customer, plus any booking result recorded by the system.

Return ONE JSON object matching this shape exactly:
{schema}

Extraction rules:
- Use ONLY what is present in the transcript or the system booking record. Never infer
  a fact the customer did not state. Use null / "unknown" / [] when it was not discussed.
- budget_min_inr and budget_max_inr are absolute rupees. "1.5 cr" is 15000000.
  "under 1.5 cr" -> min null, max 15000000. "around 1.6 cr" -> min 15000000, max 17000000.
- budget_fit compares the stated budget against the published starting prices:
  2 BHK from Rs 1,35,00,000 and 3 BHK from Rs 1,75,00,000. If the customer's ceiling
  is below the starting price of every configuration they want, that is "below_range".
- interest_level: "hot" = booked or actively agreed to a site visit; "warm" = engaged,
  gave requirements, open to a follow-up; "cold" = minimal engagement or vague;
  "not_interested" = explicitly declined or opted out.
- qualification_score is 0-100 based on budget fit, clarity of requirement, timeline,
  and site-visit intent. Put your reasoning in score_rationale in one sentence.
- do_not_contact is true ONLY if the customer explicitly asked to stop being
  contacted / remove their number / "don't call again". Asking to be called later is
  NOT do_not_contact — that is follow_up_required with follow_up_when.
- escalate_to_human is true if the customer asked for a human, was angry or abusive,
  or asked something material the agent could not answer.
- site_visit_status is "confirmed" ONLY when the system booking record shows a
  confirmed booking. If a booking was attempted and the system failed it, use
  "attempted_failed" and fill booking_failure_reason.
- summary: 2-3 sentences a human sales rep can read in five seconds.
- next_best_action: one concrete instruction for the sales team.

Output raw JSON only. No markdown, no commentary."""


def _transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        if m.get("role") == "user":
            lines.append(f"CUSTOMER: {m['content']}")
        elif m.get("role") == "assistant" and m.get("content"):
            lines.append(f"AGENT: {m['content']}")
        elif m.get("role") == "tool":
            lines.append(f"SYSTEM (booking result): {m['content']}")
    return "\n".join(lines)


EMPTY = {
    "lead": {"name": None, "phone": None, "language_preference": "unknown"},
    "requirement": {},
    "qualification": {"interest_level": "cold", "qualification_score": 0,
                      "objections_raised": [], "questions_agent_could_not_answer": []},
    "outcome": {"site_visit_status": "not_discussed", "follow_up_required": False,
                "do_not_contact": False, "escalate_to_human": False},
    "summary": "No customer messages in this conversation.",
    "next_best_action": "No action required.",
}


def generate(messages: list[dict], booking_ids: list[str] | None = None) -> dict:
    """Run the extraction pass over a finished conversation."""
    transcript = _transcript(messages)
    if not any(m.get("role") == "user" for m in messages):
        return dict(EMPTY)

    records = [BOOKINGS[b] for b in (booking_ids or []) if b in BOOKINGS]
    system_block = (
        f"\n\nSYSTEM BOOKING RECORDS: {records}" if records
        else "\n\nSYSTEM BOOKING RECORDS: none — no confirmed booking exists."
    )

    data = chat_json([
        {"role": "system", "content": EXTRACTOR_PROMPT.format(schema=ANALYTICS_SCHEMA_HINT)},
        {"role": "user", "content": f"TODAY: {date.today().isoformat()}\n\n"
                                    f"TRANSCRIPT:\n{transcript}{system_block}"},
    ], model=ANALYTICS_MODEL)

    # The booking system, not the model, is the authority on what actually booked.
    if records:
        data.setdefault("outcome", {})
        data["outcome"]["site_visit_status"] = "confirmed"
        data["outcome"]["site_visit"] = {
            "booking_id": records[-1]["booking_id"],
            "date": records[-1]["date"],
            "time_slot": records[-1]["time_slot"],
        }
    return data
