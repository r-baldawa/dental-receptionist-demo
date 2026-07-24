"""
Scheduling tools — write appointments, create calendar events, send confirmation emails.
Idempotency: check calendar_event_id / confirmation_email_sent before each call.
"""
import os
from langchain_core.tools import tool
from src.integrations.supabase_client import get_client


@tool
def create_appointment(
    patient_id: str,
    appointment_type: str,
    appointment_datetime: str,
    provider_id: str = "default",
) -> dict:
    """Create an appointment record in the database.

    Call this after confirming the appointment details with the patient.
    Always check the return value for appointment_id before calling book_calendar_event.

    ASSUMPTION (plan.md §7): provider_id defaults to "default" (single provider).
    Flag back: multi-provider calendar mapping needed once staff roster is confirmed.

    Args:
        patient_id: The patient's UUID
        appointment_type: Type of appointment, e.g. "checkup", "cleaning", "filling", "extraction", "consultation"
        appointment_datetime: ISO 8601 datetime, e.g. "2026-07-15T14:00:00" (America/Toronto timezone assumed)
        provider_id: Provider identifier — use "default" until multi-provider mapping is confirmed
    """
    client = get_client()

    # Idempotency: check for existing appointment with same patient + datetime
    existing = (
        client.table("appointments")
        .select("appointment_id, calendar_event_id, confirmation_email_sent")
        .eq("patient_id", patient_id)
        .eq("appointment_datetime", appointment_datetime)
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        return {
            "success": True,
            "appointment_id": row["appointment_id"],
            "calendar_event_id": row["calendar_event_id"],
            "confirmation_email_sent": row["confirmation_email_sent"],
            "already_existed": True,
        }

    result = (
        client.table("appointments")
        .insert({
            "patient_id": patient_id,
            "provider_id": provider_id,
            "appointment_datetime": appointment_datetime,
            "appointment_type": appointment_type,
            "status": "scheduled",
        })
        .execute()
    )

    if not result.data:
        return {"success": False, "error": "Failed to create appointment"}

    return {
        "success": True,
        "appointment_id": result.data[0]["appointment_id"],
        "calendar_event_id": None,
        "confirmation_email_sent": False,
        "already_existed": False,
    }


@tool
def book_calendar_event(
    appointment_id: str,
    patient_name: str,
    patient_email: str,
    appointment_type: str,
    appointment_datetime: str,
) -> dict:
    """Create a Google Calendar event for a confirmed appointment.

    Idempotency: only call if create_appointment returned calendar_event_id=None.

    Args:
        appointment_id: UUID from create_appointment
        patient_name: Patient's full name
        patient_email: Patient's email (added as attendee so they get a calendar invite)
        appointment_type: Type of appointment
        appointment_datetime: ISO 8601 datetime string
    """
    client = get_client()

    # Idempotency guard: check if calendar event already exists for this appointment
    existing = (
        client.table("appointments")
        .select("calendar_event_id")
        .eq("appointment_id", appointment_id)
        .limit(1)
        .execute()
    )
    if existing.data and existing.data[0].get("calendar_event_id"):
        return {"success": True, "event_id": existing.data[0]["calendar_event_id"], "already_existed": True}

    from src.integrations.google_calendar import create_appointment_event
    event_id = create_appointment_event(
        patient_name=patient_name,
        patient_email=patient_email,
        appointment_type=appointment_type,
        start_datetime=appointment_datetime,
    )

    if not event_id:
        return {"success": False, "error": "Calendar event creation failed"}

    client.table("appointments").update({"calendar_event_id": event_id}).eq("appointment_id", appointment_id).execute()
    return {"success": True, "event_id": event_id, "already_existed": False}


@tool
def send_appointment_confirmation(
    appointment_id: str,
    patient_email: str,
    patient_name: str,
    appointment_type: str,
    appointment_datetime: str,
) -> dict:
    """Send a confirmation email to the patient after their appointment is booked.

    Idempotency: only call if create_appointment returned confirmation_email_sent=False.

    Args:
        appointment_id: UUID from create_appointment
        patient_email: Patient's email address
        patient_name: Patient's full name
        appointment_type: Type of appointment
        appointment_datetime: ISO 8601 datetime string
    """
    client = get_client()

    # Idempotency guard: check if email already sent
    existing = (
        client.table("appointments")
        .select("confirmation_email_sent")
        .eq("appointment_id", appointment_id)
        .limit(1)
        .execute()
    )
    if existing.data and existing.data[0].get("confirmation_email_sent"):
        return {"success": True, "already_sent": True}

    from src.integrations.gmail_smtp import send_email
    bcc = os.getenv("CLINIC_FRONT_DESK_BCC_EMAIL") or None

    subject = f"Your appointment at Atlas Dental — {appointment_datetime[:10]}"
    body = (
        f"Hi {patient_name},\n\n"
        f"Your appointment has been booked at Atlas Dental.\n\n"
        f"Details:\n"
        f"  Type: {appointment_type.replace('_', ' ').title()}\n"
        f"  Date/Time: {appointment_datetime}\n"
        f"  Location: 123 Main Street, Toronto, ON (please check atlas-dental.ca for current address)\n\n"
        f"Please arrive 10 minutes early for your first visit.\n"
        f"To reschedule or cancel, reply to this email or call our front desk.\n\n"
        f"See you soon!\n"
        f"Atlas Dental Team"
    )

    success = send_email(to=patient_email, subject=subject, body=body, bcc=bcc)

    if success:
        client.table("appointments").update({"confirmation_email_sent": True}).eq("appointment_id", appointment_id).execute()

    return {"success": success, "already_sent": False}
