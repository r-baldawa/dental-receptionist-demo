"""
Identity resolution tool — Step 0 of every booking conversation.
Resolves new vs. existing patient via DB lookup, not self-report.
"""
from langchain_core.tools import tool
from src.integrations.supabase_client import get_client


@tool
def lookup_patient_by_contact(email: str = "", phone: str = "") -> dict:
    """Look up a patient by email and/or phone number to determine if they are new or existing.

    Call this as soon as the patient provides their email or phone number — before asking
    for any other information. The result drives the entire conversation branch.

    Args:
        email: Patient email address (pass empty string if not yet provided)
        phone: Patient phone number (pass empty string if not yet provided)

    Returns a dict with:
      - found (bool): True if an existing record was located
      - patient (dict): Full patient record if found, else None
      - match_type (str): "email", "phone", "conflict", or "none"
      - conflict (bool): True if email and phone match DIFFERENT records (flag for human review)
    """
    client = get_client()
    email = (email or "").strip().lower()
    phone = (phone or "").strip()

    email_match = None
    phone_match = None

    if email:
        result = client.table("patients").select("*").eq("email", email).limit(1).execute()
        if result.data:
            email_match = result.data[0]

    if phone:
        result = client.table("patients").select("*").eq("phone", phone).limit(1).execute()
        if result.data:
            phone_match = result.data[0]

    # Both match but to DIFFERENT records → conflict, flag for human review
    if email_match and phone_match and email_match["patient_id"] != phone_match["patient_id"]:
        return {
            "found": False,
            "patient": None,
            "match_type": "conflict",
            "conflict": True,
            "message": "Email and phone match different records. Flagging for human review.",
        }

    patient = email_match or phone_match
    if patient:
        match_type = "email" if email_match else "phone"
        return {
            "found": True,
            "patient": patient,
            "match_type": match_type,
            "conflict": False,
        }

    return {"found": False, "patient": None, "match_type": "none", "conflict": False}
