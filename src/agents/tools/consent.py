"""
Consent tools — chat-side only.

CRITICAL: There is NO sign_consent tool anywhere in this codebase.
Consent signing is in-person only via the receptionist Web App (Workflow B).
Chat-collected data is a draft with registration_status='pending_consent' until
the patient signs on a tablet at check-in. See CLAUDE.md non-negotiables.
"""
from langchain_core.tools import tool
from src.integrations.supabase_client import get_client

_CONSENT_TYPES = ["phipa_privacy", "treatment", "assignment_of_benefits", "financial_policy", "photo_id"]
_CONSENT_TEXT_VERSION = "v1.0"


@tool
def record_consent_acknowledgement(patient_id: str) -> dict:
    """Record that PHIPA consent was explained to the patient during chat.

    This does NOT sign consent — it records that the patient acknowledged
    the PHIPA explanation and agreed to proceed. Actual consent signatures
    happen in person at check-in via the receptionist Web App.

    Call this after the patient explicitly says yes to the PHIPA consent explanation,
    and BEFORE collecting any demographics or health information.

    Args:
        patient_id: The patient's UUID
    """
    client = get_client()

    # Upsert pending consent records (create_new_patient also creates these,
    # but this handles the case where records weren't created yet)
    for consent_type in _CONSENT_TYPES:
        existing = (
            client.table("consent_records")
            .select("id")
            .eq("patient_id", patient_id)
            .eq("consent_type", consent_type)
            .limit(1)
            .execute()
        )
        if not existing.data:
            client.table("consent_records").insert({
                "patient_id": patient_id,
                "consent_type": consent_type,
                "status": "pending",
                "consent_text_version": _CONSENT_TEXT_VERSION,
            }).execute()

    return {
        "success": True,
        "patient_id": patient_id,
        "message": "Consent acknowledgement recorded. Actual signatures required at check-in.",
        "pending_consent_types": _CONSENT_TYPES,
    }
