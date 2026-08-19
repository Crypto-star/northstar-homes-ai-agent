"""Runtime configuration + the single source of truth for project facts.

Every fact the agent is allowed to state lives in KNOWLEDGE_BASE. Nothing else.
If it is not in here, the agent must say it does not know and offer to check.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.getenv("MODEL", "qwen/qwen3.6-27b")
ANALYTICS_MODEL = os.getenv("ANALYTICS_MODEL", MODEL)

# Qwen3.6 emits <think> blocks by default. "none" turns that off, which we want
# for a latency-sensitive chat/voice agent. Groq only accepts "none" or "default".
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "none")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.4"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "700"))

# Comma-separated origins, or "*" for any. GitHub Pages needs the Pages origin.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# Flip to "1" to force every booking attempt to fail — used by the booking-failure
# test case and the demo video, so the failure path is reproducible on demand.
FORCE_BOOKING_FAILURE = os.getenv("FORCE_BOOKING_FAILURE", "0") == "1"

# Turns of history kept in the LLM context window (a turn = one user + one agent
# message). 40 is far beyond any realistic sales call and stays inside 131k ctx.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "40"))


KNOWLEDGE_BASE = {
    "developer": "Northstar Homes",
    "project": "Northstar One",
    "location": "Sector 79, Gurugram",
    "configurations": ["2 BHK", "3 BHK"],
    "pricing": {
        "2 BHK": "Rs 1.35 crore onwards",
        "3 BHK": "Rs 1.75 crore onwards",
    },
    "site_visit": {
        "days_open": "Monday to Saturday",
        "slots": ["11:00 AM", "1:00 PM", "3:00 PM", "5:00 PM"],
    },
}
