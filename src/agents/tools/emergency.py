"""
emergency.py — emergency tooling.

send_emergency_alert: called directly by safety_precheck.py as plain code.
  NOT registered with any agent as a discretionary tool (per CLAUDE.md non-negotiables).

send_emergency_contact_followup: a LangChain @tool for the triage_agent only.
  Fires AFTER the initial alert, once the patient has provided contact details.
"""
import os

from langchain_core.tools import tool

from src.integrations.gmail_smtp import send_emergency_alert as _send
from src.integrations.gmail_smtp import send_email


def send_emergency_alert(captured_info: dict) -> None:
    """Fire-and-forget emergency alert. Completeness is not required — speed is."""
    _send(captured_info)


@tool
def send_emergency_contact_followup(
    name: str,
    phone: str,
    email: str,
    chief_complaint: str,
) -> dict:
    """Send patient contact details to the clinic after collecting them during an emergency.

    Call this once you have confirmed the patient's full name, phone number, and email address.
    The initial emergency alert has already fired — this provides the contact info so the
    clinic team can reach the patient directly.

    Args:
        name: Patient's full name
        phone: Patient's phone number
        email: Patient's email address
        chief_complaint: One-sentence summary of the emergency from the conversation
    """
    alert_email = os.environ.get("CLINIC_EMERGENCY_ALERT_EMAIL", "")
    if not alert_email:
        return {"success": False, "error": "Emergency alert email address not configured"}

    body = (
        "DENTAL EMERGENCY - PATIENT CONTACT DETAILS\n"
        "-" * 45 + "\n\n"
        f"Patient Name:    {name}\n"
        f"Phone:           {phone}\n"
        f"Email:           {email}\n"
        f"Chief Complaint: {chief_complaint}\n\n"
        "This information was collected by the AI receptionist after the initial\n"
        "emergency alert was sent. Please follow up with the patient as soon as possible.\n"
    )

    try:
        send_email(
            to=alert_email,
            subject=f"URGENT: Emergency Contact Details — {name}",
            body=body,
        )
        return {"success": True, "name": name, "phone": phone, "email": email}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
