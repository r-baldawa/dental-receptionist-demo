"""
Receptionist Web App — Check-In & Consent Capture View (Workflow B)

Run: streamlit run src/webapp/consent_view.py

Allows a receptionist to:
1. Look up a patient by name/DOB or today's appointment list
2. Review the pre-filled registration summary
3. Capture in-person consent signatures for each required consent type
4. Submit → flips registration_status to 'active' once all required consents are signed
"""
import sys
from pathlib import Path

# Add project root to path so `src.*` imports resolve when run via streamlit
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime, timezone

import streamlit as st

from src.integrations.supabase_client import get_client

REQUIRED_CONSENT_TYPES = [
    "phipa_privacy",
    "treatment",
    "assignment_of_benefits",
    "financial_policy",
    "photo_id",
]

CONSENT_LABELS = {
    "phipa_privacy": "PHIPA Privacy Notice",
    "treatment": "Consent to Treatment",
    "assignment_of_benefits": "Assignment of Benefits",
    "financial_policy": "Financial Policy",
    "photo_id": "Photo ID Verified",
}

CONSENT_TEXT_VERSION = "v1.0"


def _lookup_patient(name: str, dob: str) -> list[dict]:
    client = get_client()
    result = (
        client.table("patients")
        .select("patient_id, full_name, dob, email, phone, registration_status, insurance, medical_flags, dental_history")
        .ilike("full_name", f"%{name}%")
        .execute()
    )
    rows = result.data or []
    if dob:
        rows = [r for r in rows if r.get("dob", "") == dob]
    return rows


def _get_consent_records(patient_id: str) -> list[dict]:
    client = get_client()
    result = (
        client.table("consent_records")
        .select("*")
        .eq("patient_id", patient_id)
        .execute()
    )
    return result.data or []


def _get_today_appointments() -> list[dict]:
    client = get_client()
    today = datetime.now(timezone.utc).date().isoformat()
    result = (
        client.table("appointments")
        .select("appointment_id, patient_id, appointment_datetime, appointment_type, patients(full_name, dob, registration_status)")
        .gte("appointment_datetime", f"{today}T00:00:00")
        .lte("appointment_datetime", f"{today}T23:59:59")
        .execute()
    )
    return result.data or []


def _sign_consent(patient_id: str, consent_type: str) -> bool:
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    existing = (
        client.table("consent_records")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("consent_type", consent_type)
        .limit(1)
        .execute()
    )

    if existing.data:
        client.table("consent_records").update({
            "status": "signed",
            "signed_at": now,
            "method": "in_person_tablet",
            "consent_text_version": CONSENT_TEXT_VERSION,
        }).eq("patient_id", patient_id).eq("consent_type", consent_type).execute()
    else:
        client.table("consent_records").insert({
            "patient_id": patient_id,
            "consent_type": consent_type,
            "status": "signed",
            "signed_at": now,
            "method": "in_person_tablet",
            "consent_text_version": CONSENT_TEXT_VERSION,
        }).execute()

    # Write audit log entry
    client.table("audit_log").insert({
        "event_type": "consent_signed",
        "patient_id": patient_id,
        "detail": {"consent_type": consent_type, "method": "in_person_tablet", "version": CONSENT_TEXT_VERSION},
    }).execute()

    return True


def _decline_consent(patient_id: str, consent_type: str) -> bool:
    client = get_client()

    existing = (
        client.table("consent_records")
        .select("id")
        .eq("patient_id", patient_id)
        .eq("consent_type", consent_type)
        .limit(1)
        .execute()
    )

    if existing.data:
        client.table("consent_records").update({
            "status": "declined",
        }).eq("patient_id", patient_id).eq("consent_type", consent_type).execute()
    else:
        client.table("consent_records").insert({
            "patient_id": patient_id,
            "consent_type": consent_type,
            "status": "declined",
            "consent_text_version": CONSENT_TEXT_VERSION,
        }).execute()

    return True


def _check_and_activate(patient_id: str) -> bool:
    """Flip registration_status to 'active' if all required consents are signed."""
    records = _get_consent_records(patient_id)
    status_map = {r["consent_type"]: r["status"] for r in records}

    all_signed = all(
        status_map.get(ct) == "signed" for ct in REQUIRED_CONSENT_TYPES
    )

    if all_signed:
        get_client().table("patients").update(
            {"registration_status": "active"}
        ).eq("patient_id", patient_id).execute()

    return all_signed


def _render_patient_summary(patient: dict) -> None:
    st.subheader("Patient Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Name:** {patient.get('full_name', '—')}")
        st.write(f"**DOB:** {patient.get('dob', '—')}")
        st.write(f"**Email:** {patient.get('email', '—')}")
        st.write(f"**Phone:** {patient.get('phone', '—')}")
    with col2:
        st.write(f"**Status:** `{patient.get('registration_status', '—')}`")
        ins = patient.get("insurance") or {}
        st.write(f"**Insurance:** {ins.get('carrier', 'None / Self-pay')}")

    med = patient.get("medical_flags") or {}
    if any(med.get(k) for k in ["allergies", "medications", "conditions"]):
        st.markdown("**Medical Flags** *(self-reported, pending clinical review)*")
        if med.get("allergies"):
            st.write(f"  • Allergies: {med['allergies']}")
        if med.get("medications"):
            st.write(f"  • Medications: {med['medications']}")
        if med.get("conditions"):
            st.write(f"  • Conditions: {med['conditions']}")

    dental = patient.get("dental_history") or {}
    if dental.get("chief_complaint"):
        st.write(f"**Chief Complaint:** {dental['chief_complaint']}")


def _render_consent_section(patient_id: str) -> None:
    st.subheader("Consent Items")
    records = _get_consent_records(patient_id)
    status_map = {r["consent_type"]: r for r in records}

    all_done = True
    for ct in REQUIRED_CONSENT_TYPES:
        record = status_map.get(ct, {})
        current_status = record.get("status", "pending")
        label = CONSENT_LABELS[ct]

        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            if current_status == "signed":
                st.success(f"✓ {label}")
            elif current_status == "declined":
                st.error(f"✗ {label} — Declined")
            else:
                st.write(f"⬜ {label}")
                all_done = False

        if current_status not in ("signed", "declined"):
            with col2:
                if st.button("Sign", key=f"sign_{ct}_{patient_id}"):
                    _sign_consent(patient_id, ct)
                    st.rerun()
            with col3:
                if st.button("Decline", key=f"decline_{ct}_{patient_id}"):
                    _decline_consent(patient_id, ct)
                    st.rerun()

    st.divider()
    if _check_and_activate(patient_id):
        st.success("✅ All required consents signed — patient is now **Active**.")
    else:
        unsigned = [
            CONSENT_LABELS[ct]
            for ct in REQUIRED_CONSENT_TYPES
            if status_map.get(ct, {}).get("status") != "signed"
        ]
        if unsigned:
            st.info(f"Waiting for: {', '.join(unsigned)}")


# ── Main app ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Atlas Dental — Check-In", layout="wide")
st.title("Atlas Dental — Check-In & Consent Capture")

tab_search, tab_today = st.tabs(["🔍 Search Patient", "📅 Today's Appointments"])

with tab_search:
    st.subheader("Find Patient")
    col_name, col_dob = st.columns(2)
    with col_name:
        search_name = st.text_input("Patient name (partial OK)")
    with col_dob:
        search_dob = st.text_input("Date of birth (YYYY-MM-DD, optional)")

    if st.button("Search") and search_name:
        results = _lookup_patient(search_name, search_dob)
        if not results:
            st.warning("No patients found.")
        else:
            st.session_state["search_results"] = results

    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        if len(results) == 1:
            selected = results[0]
        else:
            options = {f"{r['full_name']} — {r['dob']} ({r['registration_status']})": r for r in results}
            choice = st.selectbox("Select patient", list(options.keys()))
            selected = options[choice]

        st.divider()
        _render_patient_summary(selected)
        st.divider()
        _render_consent_section(selected["patient_id"])

with tab_today:
    st.subheader("Today's Appointments")
    appointments = _get_today_appointments()
    if not appointments:
        st.info("No appointments scheduled for today.")
    else:
        for appt in appointments:
            patient_info = appt.get("patients") or {}
            name = patient_info.get("full_name", "Unknown")
            status = patient_info.get("registration_status", "—")
            time_str = appt.get("appointment_datetime", "")[:16].replace("T", " ")
            appt_type = appt.get("appointment_type", "—")

            with st.expander(f"{time_str} — {name} ({appt_type}) — Status: {status}"):
                if st.button("Open check-in", key=f"checkin_{appt['appointment_id']}"):
                    # Fetch full patient record
                    r = get_client().table("patients").select("*").eq("patient_id", appt["patient_id"]).limit(1).execute()
                    if r.data:
                        st.session_state["checkin_patient"] = r.data[0]
                        st.rerun()

if "checkin_patient" in st.session_state:
    patient = st.session_state["checkin_patient"]
    st.divider()
    st.subheader(f"Check-In: {patient['full_name']}")
    _render_patient_summary(patient)
    st.divider()
    _render_consent_section(patient["patient_id"])
    if st.button("← Back to appointments"):
        del st.session_state["checkin_patient"]
        st.rerun()
