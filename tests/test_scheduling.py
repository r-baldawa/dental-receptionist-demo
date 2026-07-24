"""
Tests for scheduling tools — TC-A12 (idempotency).

Invariants:
- create_appointment: second call with same patient+datetime returns existing row, already_existed=True.
- book_calendar_event: if calendar_event_id already set on the appointment, skips creation.
- send_appointment_confirmation: if confirmation_email_sent=True, skips re-send.
- Only one calendar event and one confirmation email are ever created per appointment.
"""
from unittest.mock import MagicMock, patch

from src.agents.tools.scheduling import (
    book_calendar_event,
    create_appointment,
    send_appointment_confirmation,
)
from tests.conftest import sb_chain

_DT = "2026-08-15T10:00:00"
_APPT_ID = "appt-uuid-1"


# ---------------------------------------------------------------------------
# create_appointment
# ---------------------------------------------------------------------------

def test_create_appointment_new():
    client = MagicMock()
    # First select: no existing appointment
    # Then insert: returns new row
    select_chain = sb_chain([])
    insert_chain = sb_chain([{
        "appointment_id": _APPT_ID,
        "calendar_event_id": None,
        "confirmation_email_sent": False,
    }])

    call_count = {"n": 0}

    def table_side(name):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return select_chain
        return insert_chain

    client.table.side_effect = table_side

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        result = create_appointment.invoke({
            "patient_id": "p1",
            "appointment_type": "cleaning",
            "appointment_datetime": _DT,
        })

    assert result["success"] is True
    assert result["appointment_id"] == _APPT_ID
    assert result["already_existed"] is False


def test_create_appointment_idempotent():
    """Second call with same patient+datetime returns existing row without inserting."""
    existing_row = {
        "appointment_id": _APPT_ID,
        "calendar_event_id": "cal-123",
        "confirmation_email_sent": True,
    }
    client = MagicMock()
    client.table.return_value = sb_chain([existing_row])

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        result = create_appointment.invoke({
            "patient_id": "p1",
            "appointment_type": "cleaning",
            "appointment_datetime": _DT,
        })

    assert result["success"] is True
    assert result["already_existed"] is True
    assert result["appointment_id"] == _APPT_ID
    assert result["calendar_event_id"] == "cal-123"


# ---------------------------------------------------------------------------
# book_calendar_event — idempotency (TC-A12)
# ---------------------------------------------------------------------------

def test_book_calendar_event_skips_if_already_booked():
    """If appointment already has a calendar_event_id, no new event is created."""
    client = MagicMock()
    client.table.return_value = sb_chain([{"calendar_event_id": "existing-event-id"}])

    mock_create_event = MagicMock()

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        with patch("src.integrations.google_calendar.create_appointment_event", mock_create_event):
            result = book_calendar_event.invoke({
                "appointment_id": _APPT_ID,
                "patient_name": "Jane Doe",
                "patient_email": "jane@example.com",
                "appointment_type": "cleaning",
                "appointment_datetime": _DT,
            })

    assert result["success"] is True
    assert result["already_existed"] is True
    assert result["event_id"] == "existing-event-id"
    mock_create_event.assert_not_called()


def test_book_calendar_event_creates_when_missing():
    """When no calendar event exists, creates one and updates DB."""
    client = MagicMock()
    select_chain = sb_chain([{"calendar_event_id": None}])
    update_chain = sb_chain([])

    call_n = {"n": 0}

    def table_side(_name):
        call_n["n"] += 1
        return select_chain if call_n["n"] == 1 else update_chain

    client.table.side_effect = table_side

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        with patch(
            "src.integrations.google_calendar.create_appointment_event",
            return_value="new-event-id",
        ):
            # Need to also patch the import inside the function
            with patch(
                "src.agents.tools.scheduling.book_calendar_event.func",
                wraps=book_calendar_event.func,
            ):
                result = book_calendar_event.invoke({
                    "appointment_id": _APPT_ID,
                    "patient_name": "Jane Doe",
                    "patient_email": "jane@example.com",
                    "appointment_type": "cleaning",
                    "appointment_datetime": _DT,
                })

    assert result["success"] is True
    assert result["already_existed"] is False


# ---------------------------------------------------------------------------
# send_appointment_confirmation — idempotency (TC-A12)
# ---------------------------------------------------------------------------

def test_send_confirmation_skips_if_already_sent():
    """If confirmation_email_sent=True, email is not sent again."""
    client = MagicMock()
    client.table.return_value = sb_chain([{"confirmation_email_sent": True}])

    mock_send = MagicMock(return_value=True)

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        with patch("src.integrations.gmail_smtp.send_email", mock_send):
            result = send_appointment_confirmation.invoke({
                "appointment_id": _APPT_ID,
                "patient_email": "jane@example.com",
                "patient_name": "Jane Doe",
                "appointment_type": "cleaning",
                "appointment_datetime": _DT,
            })

    assert result["success"] is True
    assert result["already_sent"] is True
    mock_send.assert_not_called()


def test_send_confirmation_sends_when_not_yet_sent():
    client = MagicMock()
    select_chain = sb_chain([{"confirmation_email_sent": False}])
    update_chain = sb_chain([])

    call_n = {"n": 0}

    def table_side(_name):
        call_n["n"] += 1
        return select_chain if call_n["n"] == 1 else update_chain

    client.table.side_effect = table_side

    with patch("src.agents.tools.scheduling.get_client", return_value=client):
        with patch("src.integrations.gmail_smtp.send_email", return_value=True):
            result = send_appointment_confirmation.invoke({
                "appointment_id": _APPT_ID,
                "patient_email": "jane@example.com",
                "patient_name": "Jane Doe",
                "appointment_type": "cleaning",
                "appointment_datetime": _DT,
            })

    assert result["success"] is True
    assert result["already_sent"] is False
