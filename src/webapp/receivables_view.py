"""
Receivables View — Receptionist Web App (Workflow C)

Lists outstanding/overdue payment records. Receptionist selects individual patients
and triggers one email per patient. Multi-recipient send is structurally impossible
here: _send_reminder() only accepts a single patient_id — there is no batch signature.

ASSUMPTION: 7-day cooldown between reminders per patient. Flag back for clinic policy.

Run: streamlit run src/webapp/receivables_view.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import streamlit as st

from src.integrations.gmail_smtp import send_email
from src.integrations.supabase_client import get_client

COOLDOWN_DAYS = 7  # ASSUMPTION: confirm with clinic


def _get_receivables() -> list[dict]:
    client = get_client()
    result = (
        client.table("payment_records")
        .select("*, patients(patient_id, full_name, email, phone)")
        .in_("status", ["outstanding", "overdue"])
        .order("due_date")
        .execute()
    )
    return result.data or []


def _is_in_cooldown(record: dict) -> bool:
    last_sent = record.get("last_followup_sent_at")
    if not last_sent:
        return False
    last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last_dt) < timedelta(days=COOLDOWN_DAYS)


def _send_reminder(record: dict) -> dict:
    """Send one individually addressed payment reminder. Never multi-recipient.

    Accepts a single payment record (one patient). Called in a loop by the UI,
    never with a list — the loop is the caller's responsibility so each send
    is logged and any failure is isolated.
    """
    patient = record.get("patients") or {}
    patient_id = record["patient_id"]
    patient_name = patient.get("full_name", "Valued Patient")
    patient_email = patient.get("email", "")

    if not patient_email:
        return {"success": False, "patient_name": patient_name, "error": "No email on file"}

    balance = float(record["balance_amount"])
    due_date = record["due_date"]
    payment_link = record.get("payment_link", "")
    new_followup_count = record["followup_count"] + 1

    subject = "Payment Reminder — Atlas Dental"
    body = (
        f"Dear {patient_name},\n\n"
        f"This is a friendly reminder that you have an outstanding balance of "
        f"${balance:,.2f} CAD with Atlas Dental, due on {due_date}.\n\n"
        f"To settle your balance, please use the secure payment link below:\n"
        f"{payment_link}\n\n"
        f"If you have already made this payment, or if you have any questions, "
        f"please do not hesitate to contact us:\n"
        f"  ☎️  416-597-0534\n"
        f"  ✉️  info@atlasdental.ca\n\n"
        f"Thank you for being a valued patient at Atlas Dental.\n\n"
        f"Warm regards,\n"
        f"Atlas Dental Team\n"
        f"1002 Bloor Street West, Toronto, ON M6H 1M4"
    )

    success = send_email(to=patient_email, subject=subject, body=body)

    if success:
        client = get_client()
        now = datetime.now(timezone.utc).isoformat()
        client.table("payment_records").update({
            "last_followup_sent_at": now,
            "followup_count": new_followup_count,
        }).eq("id", record["id"]).execute()

        client.table("audit_log").insert({
            "event_type": "payment_reminder_sent",
            "patient_id": patient_id,
            "detail": {
                "balance_amount": balance,
                "due_date": due_date,
                "email_sent_to": patient_email,
                "followup_count": new_followup_count,
            },
        }).execute()

        return {"success": True, "patient_name": patient_name}

    return {"success": False, "patient_name": patient_name, "error": "Email send failed"}


# ── Main app ──────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Atlas Dental — Receivables", layout="wide")
st.title("Atlas Dental — Receivables Follow-Up")
st.caption(f"ASSUMPTION: {COOLDOWN_DAYS}-day reminder cooldown between sends. Confirm with clinic.")

if st.button("🔄 Refresh"):
    st.rerun()

records = _get_receivables()

if not records:
    st.success("No outstanding or overdue balances.")
    st.stop()

ready, cooldown = [], []
for r in records:
    patient = r.get("patients") or {}
    label = (
        f"{patient.get('full_name', 'Unknown')} — "
        f"${float(r['balance_amount']):,.2f} — "
        f"due {r['due_date']} — "
        f"status: {r['status']} — "
        f"reminders sent: {r['followup_count']}"
    )
    bucket = cooldown if _is_in_cooldown(r) else ready
    bucket.append({"record": r, "label": label})

st.subheader(f"{len(records)} outstanding balance(s)  —  {len(ready)} ready to remind, {len(cooldown)} in cooldown")

if cooldown:
    with st.expander(f"⏳ {len(cooldown)} patient(s) within {COOLDOWN_DAYS}-day cooldown (excluded)"):
        for d in cooldown:
            r = d["record"]
            last = (r.get("last_followup_sent_at") or "")[:10]
            st.write(f"• {d['label']}  |  last reminder: {last}")

if not ready:
    st.info("All patients with outstanding balances are within the cooldown window.")
    st.stop()

st.markdown("**Select patients to send individual reminders:**")
selected_labels = st.multiselect(
    "Patients ready for reminder",
    options=[d["label"] for d in ready],
    default=[],
    label_visibility="collapsed",
)

selected_records = [d["record"] for d in ready if d["label"] in selected_labels]

if not selected_records:
    st.stop()

st.info(
    f"**{len(selected_records)} patient(s) selected.**  "
    f"{len(selected_records)} separate email(s) will be sent — one per patient, "
    f"each containing only that patient's own balance information."
)

if st.button(f"Send {len(selected_records)} Reminder(s)", type="primary"):
    progress = st.progress(0)
    for i, record in enumerate(selected_records):
        result = _send_reminder(record)
        if result["success"]:
            st.success(f"✓ Reminder sent to {result['patient_name']}")
        else:
            st.error(f"✗ {result['patient_name']}: {result.get('error', 'Unknown error')}")
        progress.progress((i + 1) / len(selected_records))

    st.rerun()
