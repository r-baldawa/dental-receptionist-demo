"""
Escalation tools — write to audit_log and flag patient for human review.
"""
from langchain_core.tools import tool
from src.integrations.supabase_client import get_client


@tool
def flag_for_human_review(reason: str, patient_id: str = "", detail: str = "") -> dict:
    """Flag a case for human review and write an audit_log entry.

    Use this when:
    - Identity mismatch (email/phone conflict, or name/DOB doesn't match record)
    - Patient declines PHIPA consent
    - Outstanding balance blocks booking (per clinic policy)
    - Guardian/custody ambiguity for a minor patient
    - Any situation the agent cannot resolve without staff involvement

    Args:
        reason: Short reason code, e.g. "identity_mismatch", "consent_declined", "balance_overdue", "guardian_ambiguity"
        patient_id: Patient UUID if known (leave empty if identity is unresolved)
        detail: Human-readable description of what happened
    """
    client = get_client()

    event_type = "identity_mismatch" if "mismatch" in reason.lower() or "conflict" in reason.lower() else "escalation"

    audit_row = {
        "event_type": event_type,
        "patient_id": patient_id or None,
        "detail": {"reason": reason, "description": detail},
    }
    client.table("audit_log").insert(audit_row).execute()

    # If patient_id known, flip registration_status to needs_human_review
    if patient_id:
        client.table("patients").update(
            {"registration_status": "needs_human_review"}
        ).eq("patient_id", patient_id).execute()

    return {"success": True, "flagged": True, "reason": reason}
