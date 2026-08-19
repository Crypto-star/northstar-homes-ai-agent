"""Simulated site-visit booking system.

Deliberately fake — the assignment asks us to *simulate* a booking and to handle
a *failed* booking correctly. Failures here are deterministic so both the test
suite and the demo video can reproduce them on command:

  1. FORCE_BOOKING_FAILURE=1        -> every attempt fails (demo switch)
  2. Sunday                         -> site office closed
  3. slot not in the published list -> unsupported slot
  4. slot already taken             -> capacity reached

Every failure returns machine-readable alternatives so the agent can recover in
the same turn instead of dead-ending the conversation.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

from config import FORCE_BOOKING_FAILURE, KNOWLEDGE_BASE

SLOTS: list[str] = KNOWLEDGE_BASE["site_visit"]["slots"]

# (iso_date, slot) pairs that are pre-booked, so "slot full" is reachable in a demo.
_TAKEN: set[tuple[str, str]] = set()

# Seeded so the demo always has one guaranteed-full slot: this Saturday 11:00 AM.
_SEEDED = False

BOOKINGS: dict[str, dict] = {}

_WEEKDAYS = {
    "monday": 0, "mon": 0, "somvar": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "mangalvar": 1,
    "wednesday": 2, "wed": 2, "budhvar": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "guruvar": 3,
    "friday": 4, "fri": 4, "shukravar": 4,
    "saturday": 5, "sat": 5, "shanivar": 5,
    "sunday": 6, "sun": 6, "ravivar": 6, "raviwar": 6,
}


def _seed(today: date) -> None:
    global _SEEDED
    if not _SEEDED:
        saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        _TAKEN.add((saturday.isoformat(), "11:00 AM"))
        _SEEDED = True


def parse_date(text: str, today: date | None = None) -> date | None:
    """Best-effort natural-date parser for English/Hindi/Hinglish phrasings.

    Handles: ISO dates, today/aaj, tomorrow/kal, day-after/parso, weekday names
    (English + romanised Hindi), and "DD Month". Returns None if unparseable —
    the caller then asks the customer to restate the date rather than guessing.
    """
    if not text:
        return None
    today = today or date.today()
    t = text.strip().lower()

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None

    if re.search(r"\b(today|aaj|aj)\b", t):
        return today
    # "parso"/"day after" must be checked before "kal": "parso" also means kal+1.
    if re.search(r"\b(day\s*after\s*tomorrow|parso|parsu)\b", t):
        return today + timedelta(days=2)
    if re.search(r"\b(tomorrow|kal)\b", t):
        return today + timedelta(days=1)

    for name, idx in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            ahead = (idx - today.weekday()) % 7
            # "monday" said on a Monday means next Monday, not right now.
            return today + timedelta(days=ahead or 7)

    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\b", t)
    if m:
        for fmt in ("%d %b", "%d %B"):
            try:
                parsed = datetime.strptime(f"{m.group(1)} {m.group(2)[:3]}", "%d %b").date()
                year = today.year if parsed.replace(year=today.year) >= today else today.year + 1
                return parsed.replace(year=year)
            except ValueError:
                continue
    return None


def normalize_slot(text: str) -> str | None:
    """Map '11', '11am', '11:00', 'gyarah baje' -> a published slot label."""
    if not text:
        return None
    t = text.strip().lower().replace(".", "")
    words = {"gyarah": 11, "eleven": 11, "ek": 13, "one": 13, "teen": 15,
             "three": 15, "paanch": 17, "panch": 17, "five": 17}
    for word, hour24 in words.items():
        if re.search(rf"\b{word}\b", t):
            return _label(hour24)

    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        return None
    hour = int(m.group(1))
    meridiem = m.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and hour in (1, 3, 5):
        hour += 12  # site office is afternoon-only for 1/3/5
    return _label(hour)


def _label(hour24: int) -> str | None:
    label = datetime(2000, 1, 1, hour24).strftime("%I:%M %p").lstrip("0")
    return label if label in SLOTS else None


def available_slots(on: date) -> list[str]:
    _seed(date.today())
    if on.weekday() == 6:
        return []
    return [s for s in SLOTS if (on.isoformat(), s) not in _TAKEN]


def book_site_visit(
    name: str, phone: str, date_text: str, time_text: str, today: date | None = None
) -> dict:
    """Attempt a booking. Always returns a dict with an explicit `status`.

    status: "confirmed" | "failed". On failure, `reason` is a stable machine code
    and `alternatives` lists what the agent can offer instead.
    """
    today = today or date.today()
    _seed(today)
    phone = re.sub(r"\D", "", str(phone or ""))
    when = parse_date(date_text, today)
    slot = normalize_slot(time_text)

    def fail(reason: str, message: str, **extra) -> dict:
        return {"status": "failed", "reason": reason, "message": message, **extra}

    if FORCE_BOOKING_FAILURE:
        return fail(
            "system_unavailable",
            "Booking system is temporarily unavailable.",
            alternatives=[],
        )
    if len(phone) < 10:
        return fail("invalid_phone", "A valid 10-digit mobile number is required.")
    if when is None:
        return fail("unparseable_date", "Could not understand the requested date.")
    if slot is None:
        return fail(
            "invalid_slot",
            "Requested time is not one of the published site-visit slots.",
            alternatives=SLOTS,
        )
    if when < today:
        return fail("past_date", "Requested date is in the past.")
    if when.weekday() == 6:
        nxt = when + timedelta(days=1)
        return fail(
            "closed_sunday",
            "The site office is closed on Sundays.",
            alternatives=[{"date": nxt.isoformat(), "slots": available_slots(nxt)}],
        )
    if (when.isoformat(), slot) in _TAKEN:
        same_day = available_slots(when)
        nxt = when + timedelta(days=1 if when.weekday() != 5 else 2)
        return fail(
            "slot_full",
            f"The {slot} slot on {when.isoformat()} is fully booked.",
            alternatives=[
                {"date": when.isoformat(), "slots": same_day},
                {"date": nxt.isoformat(), "slots": available_slots(nxt)},
            ],
        )

    _TAKEN.add((when.isoformat(), slot))
    booking_id = f"NS1-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "status": "confirmed",
        "booking_id": booking_id,
        "name": (name or "").strip(),
        "phone": phone,
        "date": when.isoformat(),
        "day": when.strftime("%A"),
        "time_slot": slot,
        "location": KNOWLEDGE_BASE["location"],
    }
    BOOKINGS[booking_id] = record
    return record


def demo() -> None:
    """Self-check: run `python booking.py`. Fails loudly if the logic breaks."""
    today = date(2026, 8, 20)  # a Thursday
    assert parse_date("kal", today) == date(2026, 8, 21)
    assert parse_date("parso", today) == date(2026, 8, 22)
    assert parse_date("aaj", today) == today
    assert parse_date("saturday", today) == date(2026, 8, 22)
    assert parse_date("gibberish", today) is None
    assert normalize_slot("11am") == "11:00 AM"
    assert normalize_slot("3") == "3:00 PM"
    assert normalize_slot("gyarah baje") == "11:00 AM"
    assert normalize_slot("9pm") is None

    ok = book_site_visit("Rahul", "9810012345", "saturday", "1pm", today)
    assert ok["status"] == "confirmed", ok
    dupe = book_site_visit("Priya", "9810012346", "saturday", "1pm", today)
    assert dupe["reason"] == "slot_full", dupe
    assert dupe["alternatives"][0]["slots"], dupe

    sun = book_site_visit("Amit", "9810012347", "2026-08-23", "11am", today)
    assert sun["reason"] == "closed_sunday", sun
    bad = book_site_visit("Amit", "981", "saturday", "11am", today)
    assert bad["reason"] == "invalid_phone", bad
    bad_slot = book_site_visit("Amit", "9810012347", "friday", "9pm", today)
    assert bad_slot["reason"] == "invalid_slot", bad_slot
    print("booking.py self-check passed")


if __name__ == "__main__":
    demo()
