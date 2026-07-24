"""
Patient data write tools — used by booking_agent.
All writes go to Supabase. Medical data is tagged "unverified, pending clinical review".
"""
from datetime import date, datetime
from langchain_core.tools import tool
from postgrest.exceptions import APIError
from src.integrations.supabase_client import get_client

_CONSENT_TEXT_VERSION = "v1.0"
_CONSENT_TYPES = ["phipa_privacy", "treatment", "assignment_of_benefits", "financial_policy", "photo_id"]


@tool
def create_new_patient(
    full_name: str,
    dob: str,
    phone: str,
    email: str,
    address: str = "",
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
) -> dict:
    """Create a new patient record in the database with registration_status='pending_consent'.

    Call this ONLY after the patient has explicitly given PHIPA consent. Do NOT call
    before consent is obtained. Also creates pending consent_records rows for in-person signing.

    Args:
        full_name: Patient's full legal name
        dob: Date of birth in YYYY-MM-DD format
        phone: Phone number
        email: Email address (required for confirmation emails)
        address: Optional mailing address
        emergency_contact_name: Optional emergency contact name
        emergency_contact_phone: Optional emergency contact phone

    Returns dict with patient_id on success, or error message.
    """
    client = get_client()

    # Determine if minor
    try:
        dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
        today = date.today()
        is_minor = (today - dob_date).days < 18 * 365
    except ValueError:
        is_minor = False

    emergency_contact = None
    if emergency_contact_name:
        emergency_contact = {"name": emergency_contact_name, "phone": emergency_contact_phone}

    patient_row = {
        "full_name": full_name,
        "dob": dob,
        "phone": phone,
        "email": email.lower().strip(),
        "address": address or None,
        "emergency_contact": emergency_contact,
        "is_minor": is_minor,
        "registration_status": "pending_consent",
    }

    try:
        result = client.table("patients").insert(patient_row).execute()
    except APIError as e:
        if getattr(e, "code", None) == "23505":
            return {
                "success": False,
                "error": "email_already_exists",
                "message": f"A patient with email {email} already exists in the database. Call lookup_patient_by_contact with this email to retrieve their record and switch to the existing patient flow.",
            }
        return {"success": False, "error": str(e)}
    if not result.data:
        return {"success": False, "error": "Failed to create patient record"}

    patient_id = result.data[0]["patient_id"]

    # Create pending consent records for in-person signing
    consent_rows = [
        {
            "patient_id": patient_id,
            "consent_type": ct,
            "status": "pending",
            "consent_text_version": _CONSENT_TEXT_VERSION,
        }
        for ct in _CONSENT_TYPES
    ]
    client.table("consent_records").insert(consent_rows).execute()

    return {
        "success": True,
        "patient_id": patient_id,
        "is_minor": is_minor,
        "registration_status": "pending_consent",
    }


@tool
def update_patient_insurance(patient_id: str, carrier: str, policy_number: str = "", group_number: str = "", subscriber_relationship: str = "self", billing_preference: str = "") -> dict:
    """Update insurance information for an existing patient.

    Args:
        patient_id: The patient's UUID
        carrier: Insurance carrier name (e.g. "Sun Life", "Manulife")
        policy_number: Policy/certificate number
        group_number: Group number
        subscriber_relationship: Relationship to subscriber: "self", "spouse", "child", "other"
        billing_preference: Optional billing preference note
    """
    client = get_client()
    insurance = {
        "carrier": carrier,
        "policy_number": policy_number,
        "group_number": group_number,
        "subscriber_relationship": subscriber_relationship,
        "billing_preference": billing_preference,
    }
    client.table("patients").update({"insurance": insurance}).eq("patient_id", patient_id).execute()
    return {"success": True, "patient_id": patient_id}


@tool
def update_medical_history(
    patient_id: str,
    medications: str = "",
    allergies: str = "",
    conditions: str = "",
    pregnancy: bool = False,
) -> dict:
    """Update self-reported medical history for a patient.

    Data is tagged 'unverified, pending clinical review' — it is self-reported
    and must be verified by clinical staff before treatment.

    Args:
        patient_id: The patient's UUID
        medications: Current medications (free text)
        allergies: Known allergies, especially penicillin/latex/anesthetics
        conditions: Ongoing health conditions (diabetes, heart issues, bleeding disorders)
        pregnancy: Whether patient may be pregnant
    """
    client = get_client()
    medical_flags = {
        "medications": medications,
        "allergies": allergies,
        "conditions": conditions,
        "pregnancy": pregnancy,
        "_verification_status": "unverified, pending clinical review",
    }
    client.table("patients").update({"medical_flags": medical_flags}).eq("patient_id", patient_id).execute()
    return {"success": True, "patient_id": patient_id}


@tool
def update_dental_history(
    patient_id: str,
    chief_complaint: str = "",
    last_visit_date: str = "",
    previous_dentist: str = "",
    referral_source: str = "",
    habits: str = "",
) -> dict:
    """Update dental history and chief complaint for a patient.

    Args:
        patient_id: The patient's UUID
        chief_complaint: Main reason for visit / what brings them in
        last_visit_date: Approximate date of last dental visit (free text is fine)
        previous_dentist: Name/location of previous dentist if applicable
        referral_source: How they heard about Atlas Dental
        habits: Relevant habits like grinding, smoking if mentioned
    """
    client = get_client()
    dental_history = {
        "chief_complaint": chief_complaint,
        "last_visit_date": last_visit_date,
        "previous_dentist": previous_dentist,
        "referral_source": referral_source,
        "habits": habits,
    }
    client.table("patients").update({"dental_history": dental_history}).eq("patient_id", patient_id).execute()
    return {"success": True, "patient_id": patient_id}


@tool
def update_guardian_info(patient_id: str, guardian_name: str, relationship: str, guardian_phone: str = "", guardian_email: str = "") -> dict:
    """Record guardian information for a minor patient.

    Args:
        patient_id: The minor patient's UUID
        guardian_name: Full name of parent/guardian
        relationship: Relationship to patient (e.g. "mother", "father", "legal guardian")
        guardian_phone: Guardian's contact phone
        guardian_email: Guardian's email
    """
    client = get_client()
    guardian_info = {
        "name": guardian_name,
        "relationship": relationship,
        "phone": guardian_phone,
        "email": guardian_email,
    }
    client.table("patients").update({"guardian_info": guardian_info, "is_minor": True}).eq("patient_id", patient_id).execute()
    return {"success": True, "patient_id": patient_id}


@tool
def get_patient_balance(patient_id: str) -> dict:
    """Check if a patient has any outstanding or overdue payment records.

    Args:
        patient_id: The patient's UUID

    Returns dict with has_balance (bool), total_outstanding, and list of records.
    """
    client = get_client()
    result = client.table("payment_records").select("*").eq("patient_id", patient_id).in_("status", ["outstanding", "overdue"]).execute()
    records = result.data or []
    total = sum(float(r["balance_amount"]) for r in records)
    return {
        "has_balance": len(records) > 0,
        "total_outstanding": total,
        "records": records,
    }


@tool
def get_no_show_history(patient_id: str) -> dict:
    """Check a patient's no-show count to determine if a deposit is required.

    ASSUMPTION (plan.md §7): threshold of 2+ no-shows triggers deposit requirement.
    Flag back: confirm threshold with clinic.

    Args:
        patient_id: The patient's UUID
    """
    client = get_client()
    result = client.table("patients").select("no_show_count").eq("patient_id", patient_id).limit(1).execute()
    count = result.data[0]["no_show_count"] if result.data else 0
    # ASSUMPTION: threshold = 2. Flag back for clinic confirmation.
    requires_deposit = count >= 2
    return {"no_show_count": count, "requires_deposit": requires_deposit}
