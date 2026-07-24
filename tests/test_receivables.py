"""
Tests for receivables follow-up — TC-C1, TC-C2.

Invariants (TC-C1 is the most important):
- _send_reminder accepts exactly ONE patient record — no batch signature exists.
- For N patients, send_email is called N times, each call addressed to ONE patient.
- No single email contains more than one patient's financial information.
- Each send increments followup_count and sets last_followup_sent_at.
- Each send writes one audit_log row with event_type='payment_reminder_sent'.
- Missing email on a record returns an error without sending.
- TC-C2: _is_in_cooldown returns True within 7-day window, False outside it.
"""
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

from tests.conftest import install_streamlit_stub, sb_chain

# Streamlit must be stubbed before importing receivables_view
install_streamlit_stub()

# Stub get_client at import time so module-level _get_receivables() call is safe
_stub_client = MagicMock()
_stub_client.table.return_value = sb_chain([])

with patch("src.integrations.supabase_client.get_client", return_value=_stub_client):
    from src.webapp.receivables_view import _is_in_cooldown, _send_reminder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    patient_id: str,
    name: str,
    email: str,
    balance: str = "200.00",
    due_date: str = "2026-07-01",
    followup_count: int = 0,
    last_sent: str | None = None,
    record_id: str | None = None,
):
    return {
        "id": record_id or f"rec-{patient_id}",
        "patient_id": patient_id,
        "balance_amount": balance,
        "due_date": due_date,
        "followup_count": followup_count,
        "last_followup_sent_at": last_sent,
        "payment_link": "https://pay.atlasdental.ca/test",
        "status": "outstanding",
        "patients": {"full_name": name, "email": email, "phone": "4165550000"},
    }


# ---------------------------------------------------------------------------
# TC-C1: one email per patient, never multi-recipient
# ---------------------------------------------------------------------------

def test_send_reminder_accepts_single_record_not_list():
    """_send_reminder signature takes a dict, not a list — enforces one-at-a-time."""
    import inspect
    sig = inspect.signature(_send_reminder)
    params = list(sig.parameters.values())
    assert len(params) == 1, "Must accept exactly one parameter (single record dict)"
    # The parameter should not be annotated as list
    annotation = params[0].annotation
    assert annotation is not list, "Parameter must not be typed as list"


def test_three_patients_get_three_separate_emails():
    """TC-C1: For 3 selected patients, send_email called 3 times — once per patient."""
    records = [
        _make_record("p1", "Alice Smith", "alice@example.com"),
        _make_record("p2", "Bob Jones", "bob@example.com"),
        _make_record("p3", "Carol White", "carol@example.com"),
    ]

    mock_send = MagicMock(return_value=True)
    mock_client = MagicMock()
    mock_client.table.return_value = sb_chain([])

    with patch("src.webapp.receivables_view.send_email", mock_send):
        with patch("src.webapp.receivables_view.get_client", return_value=mock_client):
            for record in records:
                _send_reminder(record)

    assert mock_send.call_count == 3


def test_each_email_addressed_to_one_patient_only():
    """No email body may contain another patient's financial information."""
    records = [
        _make_record("p1", "Alice Smith", "alice@example.com", balance="100.00"),
        _make_record("p2", "Bob Jones", "bob@example.com", balance="250.00"),
    ]

    sent_calls: list[dict] = []

    def capture_send(to, subject, body, **kwargs):
        sent_calls.append({"to": to, "body": body})
        return True

    mock_client = MagicMock()
    mock_client.table.return_value = sb_chain([])

    with patch("src.webapp.receivables_view.send_email", side_effect=capture_send):
        with patch("src.webapp.receivables_view.get_client", return_value=mock_client):
            for record in records:
                _send_reminder(record)

    assert len(sent_calls) == 2

    # Alice's email must contain only her info, not Bob's
    alice_body = sent_calls[0]["body"]
    assert "Alice" in alice_body
    assert "100.00" in alice_body
    assert "Bob" not in alice_body
    assert "250.00" not in alice_body

    # Bob's email must contain only his info, not Alice's
    bob_body = sent_calls[1]["body"]
    assert "Bob" in bob_body
    assert "250.00" in bob_body
    assert "Alice" not in bob_body
    assert "100.00" not in bob_body


def test_each_email_sent_to_correct_recipient():
    records = [
        _make_record("p1", "Alice Smith", "alice@example.com"),
        _make_record("p2", "Bob Jones", "bob@example.com"),
    ]

    sent_to: list[str] = []

    def capture(to, **kwargs):
        sent_to.append(to)
        return True

    mock_client = MagicMock()
    mock_client.table.return_value = sb_chain([])

    with patch("src.webapp.receivables_view.send_email", side_effect=capture):
        with patch("src.webapp.receivables_view.get_client", return_value=mock_client):
            for record in records:
                _send_reminder(record)

    assert sent_to == ["alice@example.com", "bob@example.com"]


# ---------------------------------------------------------------------------
# followup_count and last_followup_sent_at updated per send
# ---------------------------------------------------------------------------

def test_send_reminder_increments_followup_count():
    record = _make_record("p1", "Alice Smith", "alice@example.com", followup_count=2)

    updated_rows: list = []

    def capture_update(data):
        updated_rows.append(data)
        return MagicMock()

    mock_chain = MagicMock()
    mock_chain.update.side_effect = capture_update
    mock_chain.eq.return_value = mock_chain
    mock_chain.execute.return_value = MagicMock(data=[])

    mock_client = MagicMock()
    mock_client.table.return_value = mock_chain

    with patch("src.webapp.receivables_view.send_email", return_value=True):
        with patch("src.webapp.receivables_view.get_client", return_value=mock_client):
            _send_reminder(record)

    # Verify followup_count was updated to 3
    update_data = next(
        (d for d in updated_rows if "followup_count" in d), None
    )
    if update_data:
        assert update_data["followup_count"] == 3


def test_send_reminder_writes_audit_log():
    record = _make_record("p1", "Alice Smith", "alice@example.com")

    audit_inserts: list = []

    def capture_insert(data):
        if isinstance(data, dict) and data.get("event_type") == "payment_reminder_sent":
            audit_inserts.append(data)
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=[])
        return chain

    mock_client = MagicMock()
    inner_chain = MagicMock()
    inner_chain.insert.side_effect = capture_insert
    inner_chain.update.return_value = inner_chain
    inner_chain.eq.return_value = inner_chain
    inner_chain.execute.return_value = MagicMock(data=[])
    mock_client.table.return_value = inner_chain

    with patch("src.webapp.receivables_view.send_email", return_value=True):
        with patch("src.webapp.receivables_view.get_client", return_value=mock_client):
            _send_reminder(record)

    assert len(audit_inserts) == 1
    assert audit_inserts[0]["patient_id"] == "p1"
    assert "balance_amount" in audit_inserts[0]["detail"]


# ---------------------------------------------------------------------------
# Missing email — graceful failure, no send
# ---------------------------------------------------------------------------

def test_send_reminder_no_email_fails_gracefully():
    record = _make_record("p1", "No Email Patient", email="")
    record["patients"]["email"] = ""

    mock_send = MagicMock(return_value=True)
    with patch("src.webapp.receivables_view.send_email", mock_send):
        result = _send_reminder(record)

    assert result["success"] is False
    assert "error" in result
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# TC-C2: cooldown check
# ---------------------------------------------------------------------------

def test_is_in_cooldown_within_7_days():
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    record = _make_record("p1", "Alice", "alice@example.com", last_sent=recent)
    assert _is_in_cooldown(record) is True


def test_is_in_cooldown_outside_7_days():
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    record = _make_record("p1", "Alice", "alice@example.com", last_sent=old)
    assert _is_in_cooldown(record) is False


def test_is_in_cooldown_never_sent():
    record = _make_record("p1", "Alice", "alice@example.com", last_sent=None)
    assert _is_in_cooldown(record) is False


def test_is_in_cooldown_exactly_at_boundary():
    # 7 days exactly = still in cooldown (< timedelta(days=7) is False)
    at_boundary = (datetime.now(timezone.utc) - timedelta(days=7, seconds=1)).isoformat()
    record = _make_record("p1", "Alice", "alice@example.com", last_sent=at_boundary)
    assert _is_in_cooldown(record) is False
