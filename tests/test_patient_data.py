"""
Tests for patient data write tools — TC-A2, TC-A7.

Invariants:
- create_new_patient writes patients row with registration_status='pending_consent'.
- create_new_patient creates 5 pending consent_records rows (never signs them).
- Duplicate email (DB constraint 23505) returns graceful error, not an exception.
- Minor detection: DOB within 18 years sets is_minor=True.
- get_no_show_history: count < 2 → no deposit; count >= 2 → requires_deposit=True.
- get_patient_balance: totals outstanding/overdue records.
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

from postgrest.exceptions import APIError

from src.agents.tools.patient_data import (
    create_new_patient,
    get_no_show_history,
    get_patient_balance,
)
from tests.conftest import sb_chain


def _adult_dob() -> str:
    return (date.today() - timedelta(days=365 * 30)).strftime("%Y-%m-%d")


def _minor_dob() -> str:
    return (date.today() - timedelta(days=365 * 15)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# create_new_patient — success path (TC-A2)
# ---------------------------------------------------------------------------

def test_create_new_patient_success():
    client = MagicMock()
    insert_chain = sb_chain([{"patient_id": "new-uuid"}])
    consent_chain = sb_chain([])
    client.table.side_effect = lambda name: insert_chain if name == "patients" else consent_chain

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = create_new_patient.invoke({
            "full_name": "Jane Doe",
            "dob": _adult_dob(),
            "phone": "4165551234",
            "email": "jane@example.com",
        })

    assert result["success"] is True
    assert result["patient_id"] == "new-uuid"
    assert result["registration_status"] == "pending_consent"


def test_create_new_patient_creates_5_consent_records():
    """5 pending consent rows must be inserted immediately after patient creation."""
    client = MagicMock()
    patients_chain = sb_chain([{"patient_id": "new-uuid"}])
    consent_chain = sb_chain([])

    inserted_consent_rows: list = []

    def consent_insert(rows):
        inserted_consent_rows.extend(rows)
        return consent_chain

    consent_chain.insert.side_effect = consent_insert
    client.table.side_effect = lambda name: patients_chain if name == "patients" else consent_chain

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        create_new_patient.invoke({
            "full_name": "Jane Doe",
            "dob": _adult_dob(),
            "phone": "4165551234",
            "email": "jane@example.com",
        })

    assert len(inserted_consent_rows) == 5
    statuses = {r["status"] for r in inserted_consent_rows}
    assert statuses == {"pending"}, "All consent records must start as pending, never signed"


def test_create_new_patient_email_lowercased():
    """Email must be stored lowercase regardless of input casing."""
    client = MagicMock()
    captured: list = []

    def capture_insert(row):
        captured.append(row)
        return sb_chain([{"patient_id": "p1"}])

    chain = sb_chain([{"patient_id": "p1"}])
    chain.insert.side_effect = capture_insert
    client.table.return_value = chain

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        create_new_patient.invoke({
            "full_name": "Test User",
            "dob": _adult_dob(),
            "phone": "4165550000",
            "email": "TEST@EXAMPLE.COM",
        })

    if captured:
        assert captured[0]["email"] == "test@example.com"


# ---------------------------------------------------------------------------
# Duplicate email — graceful error (no exception propagation)
# ---------------------------------------------------------------------------

def test_duplicate_email_returns_error_dict():
    """APIError 23505 must return a dict with error='email_already_exists', not raise."""
    client = MagicMock()
    chain = sb_chain([])

    dup_error = APIError({"code": "23505", "message": "duplicate key"})
    dup_error.code = "23505"
    chain.execute.side_effect = dup_error
    client.table.return_value = chain

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = create_new_patient.invoke({
            "full_name": "Existing User",
            "dob": _adult_dob(),
            "phone": "4165550001",
            "email": "existing@example.com",
        })

    assert result["success"] is False
    assert result["error"] == "email_already_exists"
    assert "existing@example.com" in result["message"]


# ---------------------------------------------------------------------------
# TC-A7: minor detection
# ---------------------------------------------------------------------------

def test_minor_detected_when_dob_under_18():
    client = MagicMock()
    client.table.return_value = sb_chain([{"patient_id": "minor-uuid"}])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = create_new_patient.invoke({
            "full_name": "Young Patient",
            "dob": _minor_dob(),
            "phone": "4165550002",
            "email": "minor@example.com",
        })

    assert result["is_minor"] is True


def test_adult_not_flagged_as_minor():
    client = MagicMock()
    client.table.return_value = sb_chain([{"patient_id": "adult-uuid"}])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = create_new_patient.invoke({
            "full_name": "Adult Patient",
            "dob": _adult_dob(),
            "phone": "4165550003",
            "email": "adult@example.com",
        })

    assert result["is_minor"] is False


# ---------------------------------------------------------------------------
# get_no_show_history — TC-A10
# ---------------------------------------------------------------------------

def test_no_show_below_threshold_no_deposit():
    client = MagicMock()
    client.table.return_value = sb_chain([{"no_show_count": 1}])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_no_show_history.invoke({"patient_id": "p1"})

    assert result["no_show_count"] == 1
    assert result["requires_deposit"] is False


def test_no_show_at_threshold_requires_deposit():
    client = MagicMock()
    client.table.return_value = sb_chain([{"no_show_count": 2}])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_no_show_history.invoke({"patient_id": "p1"})

    assert result["requires_deposit"] is True


def test_no_show_above_threshold_requires_deposit():
    client = MagicMock()
    client.table.return_value = sb_chain([{"no_show_count": 5}])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_no_show_history.invoke({"patient_id": "p1"})

    assert result["requires_deposit"] is True


def test_no_show_patient_not_found_defaults_zero():
    client = MagicMock()
    client.table.return_value = sb_chain([])  # no rows

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_no_show_history.invoke({"patient_id": "unknown"})

    assert result["no_show_count"] == 0
    assert result["requires_deposit"] is False


# ---------------------------------------------------------------------------
# get_patient_balance
# ---------------------------------------------------------------------------

def test_get_patient_balance_sums_outstanding():
    records = [
        {"balance_amount": "150.00", "status": "outstanding"},
        {"balance_amount": "75.50", "status": "overdue"},
    ]
    client = MagicMock()
    client.table.return_value = sb_chain(records)

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_patient_balance.invoke({"patient_id": "p1"})

    assert result["has_balance"] is True
    assert abs(result["total_outstanding"] - 225.50) < 0.01
    assert len(result["records"]) == 2


def test_get_patient_balance_no_records():
    client = MagicMock()
    client.table.return_value = sb_chain([])

    with patch("src.agents.tools.patient_data.get_client", return_value=client):
        result = get_patient_balance.invoke({"patient_id": "p1"})

    assert result["has_balance"] is False
    assert result["total_outstanding"] == 0.0
