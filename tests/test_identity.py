"""
Tests for lookup_patient_by_contact — TC-A1, TC-A3.

Invariants:
- Identity is resolved via DB lookup (email/phone), never by self-report.
- Email match and phone match to the SAME record → found=True, no conflict.
- Email and phone match DIFFERENT records → conflict=True, found=False.
- No match → found=False, match_type="none".
"""
from unittest.mock import patch

from src.agents.tools.identity import lookup_patient_by_contact
from tests.conftest import make_client, sb_chain

_PATIENT_A = {
    "patient_id": "uuid-a",
    "full_name": "Alice Smith",
    "email": "alice@example.com",
    "phone": "4165550001",
    "dob": "1985-03-15",
}

_PATIENT_B = {
    "patient_id": "uuid-b",
    "full_name": "Bob Jones",
    "email": "bob@example.com",
    "phone": "4165550002",
    "dob": "1990-07-20",
}


def _patch_client(email_data=None, phone_data=None):
    """
    Returns a mock client where:
    - .eq("email", ...) → email_data
    - .eq("phone", ...) → phone_data
    """
    import unittest.mock as _m

    chain = _m.MagicMock()

    def _eq(col, val):
        inner = _m.MagicMock()
        if col == "email":
            inner.execute.return_value = _m.MagicMock(data=email_data or [])
        elif col == "phone":
            inner.execute.return_value = _m.MagicMock(data=phone_data or [])
        else:
            inner.execute.return_value = _m.MagicMock(data=[])
        inner.limit.return_value = inner
        inner.eq.side_effect = _eq
        return inner

    chain.eq.side_effect = _eq
    chain.select.return_value = chain
    chain.limit.return_value = chain

    client = _m.MagicMock()
    client.table.return_value = chain
    return client


# ---------------------------------------------------------------------------
# Email match
# ---------------------------------------------------------------------------

def test_email_match_found():
    client = _patch_client(email_data=[_PATIENT_A])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke({"email": "alice@example.com", "phone": ""})
    assert result["found"] is True
    assert result["patient"]["patient_id"] == "uuid-a"
    assert result["match_type"] == "email"
    assert result["conflict"] is False


def test_email_match_lowercases_input():
    """Emails are stored lowercase; lookup must normalise."""
    client = _patch_client(email_data=[_PATIENT_A])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke({"email": "ALICE@EXAMPLE.COM", "phone": ""})
    assert result["found"] is True


# ---------------------------------------------------------------------------
# Phone match
# ---------------------------------------------------------------------------

def test_phone_match_found():
    client = _patch_client(phone_data=[_PATIENT_A])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke({"email": "", "phone": "4165550001"})
    assert result["found"] is True
    assert result["match_type"] == "phone"
    assert result["conflict"] is False


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------

def test_no_match_returns_found_false():
    client = _patch_client(email_data=[], phone_data=[])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke({"email": "new@example.com", "phone": ""})
    assert result["found"] is False
    assert result["match_type"] == "none"
    assert result["conflict"] is False
    assert result["patient"] is None


# ---------------------------------------------------------------------------
# TC-A3: conflict — email and phone match DIFFERENT records
# ---------------------------------------------------------------------------

def test_conflict_different_records():
    """Email → Patient A, Phone → Patient B → conflict=True, found=False."""
    client = _patch_client(email_data=[_PATIENT_A], phone_data=[_PATIENT_B])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke(
            {"email": "alice@example.com", "phone": "4165550002"}
        )
    assert result["conflict"] is True
    assert result["found"] is False
    assert result["match_type"] == "conflict"
    assert result["patient"] is None


# ---------------------------------------------------------------------------
# Same record matched by both email and phone → no conflict
# ---------------------------------------------------------------------------

def test_same_record_both_channels_no_conflict():
    client = _patch_client(email_data=[_PATIENT_A], phone_data=[_PATIENT_A])
    with patch("src.agents.tools.identity.get_client", return_value=client):
        result = lookup_patient_by_contact.invoke(
            {"email": "alice@example.com", "phone": "4165550001"}
        )
    assert result["conflict"] is False
    assert result["found"] is True
    assert result["patient"]["patient_id"] == "uuid-a"
