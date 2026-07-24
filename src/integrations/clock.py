"""
clock.py — current date/time context for agent prompts.
LLMs have no innate sense of "today"; without this, agents infer a plausible-looking
date from training data instead of the real one, and can propose past dates for booking.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo


def get_current_context_line() -> str:
    tz_name = os.getenv("CLINIC_BUSINESS_HOURS_TZ", "America/Toronto")
    now = datetime.now(ZoneInfo(tz_name))
    return (
        f"[System context — current date/time: {now.strftime('%A, %B %d, %Y, %I:%M %p')} "
        f"({tz_name}). Never propose or confirm an appointment date/time before this.]"
    )
