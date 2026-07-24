"""
Google Calendar integration — OAuth2 (same credentials as Gmail).
Creates appointment events and queries free/busy slots.
"""
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

# ASSUMPTION (plan.md §7): default durations — confirm exact values with clinic.
_DURATION_MINUTES = {
    "checkup": 30,
    "cleaning": 30,
    "consultation": 30,
    "filling": 60,
    "extraction": 60,
    "root_canal": 90,
    "crown": 60,
    "default": 30,
}


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


def _default_calendar_id() -> str:
    return os.environ.get("GOOGLE_CALENDAR_ID", "primary")


def create_appointment_event(
    patient_name: str,
    patient_email: str,
    appointment_type: str,
    start_datetime: str,
    provider_calendar_id: str | None = None,
) -> str | None:
    """Create a calendar event; return the event_id or None on failure.

    ASSUMPTION (plan.md §7): default duration 30 min for checkup/cleaning,
    60 min for procedures. Flag back: confirm exact per-type durations with clinic.

    ASSUMPTION (plan.md §7): single default calendar when provider_calendar_id is None.
    Flag back: multi-provider calendar mapping needed once staff roster is confirmed.
    """
    calendar_id = provider_calendar_id or _default_calendar_id()
    duration = _DURATION_MINUTES.get(appointment_type.lower(), _DURATION_MINUTES["default"])

    start = datetime.fromisoformat(start_datetime)
    end = start + timedelta(minutes=duration)

    event = {
        "summary": f"Dental Appointment — {patient_name}",
        "description": f"Type: {appointment_type}\nPatient: {patient_name}",
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Toronto"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Toronto"},
        "attendees": [{"email": patient_email}],
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "email", "minutes": 1440}],  # 24h reminder
        },
    }

    result = (
        _get_service()
        .events()
        .insert(calendarId=calendar_id, body=event, sendUpdates="all")
        .execute()
    )
    event_id = result.get("id")
    print(f"[google_calendar] created event {event_id!r} for {patient_name!r}")
    return event_id


def get_available_slots(
    calendar_id: str,
    date_range_start: str,
    date_range_end: str,
) -> list[dict]:
    """Return busy blocks in the given range via the free/busy endpoint."""
    service = _get_service()
    body = {
        "timeMin": date_range_start,
        "timeMax": date_range_end,
        "items": [{"id": calendar_id}],
    }
    result = service.freebusy().query(body=body).execute()
    busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
    return busy
