"""
Tests for safety_precheck_node — TC-A4, TC-A5, TC-A6.

Invariants:
- Emergency keywords fire send_emergency_alert and set is_emergency=True.
- active_specialist is pre-set to "triage" on emergency detection.
- Once is_emergency=True, the alert does NOT re-fire on subsequent turns.
- Non-emergency messages never trigger the alert.
- turn_count increments on every call regardless.
"""
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from src.agents.safety_precheck import safety_precheck_node


def _state(**kwargs):
    base = {
        "messages": [],
        "is_emergency": False,
        "patient_id": None,
        "demographics": {},
        "turn_count": 0,
        "channel": "chat",
        "active_specialist": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Emergency keyword detection
# ---------------------------------------------------------------------------

def test_emergency_keyword_sets_is_emergency():
    state = _state(messages=[HumanMessage(content="I have severe pain in my jaw")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


def test_emergency_keyword_presets_triage_specialist():
    state = _state(messages=[HumanMessage(content="I have severe pain")])
    with patch("src.agents.safety_precheck.send_emergency_alert"):
        result = safety_precheck_node(state)
    assert result["active_specialist"] == "triage"


def test_emergency_keyword_case_insensitive():
    state = _state(messages=[HumanMessage(content="My tooth TRAUMA is awful")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


def test_knocked_out_tooth_triggers_emergency():
    state = _state(messages=[HumanMessage(content="I knocked out my tooth")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


def test_abscess_triggers_emergency():
    state = _state(messages=[HumanMessage(content="I think I have an abscess")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# Non-emergency messages
# ---------------------------------------------------------------------------

def test_routine_message_no_alert():
    state = _state(messages=[HumanMessage(content="I'd like to book a cleaning")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result.get("is_emergency") is None or result.get("is_emergency") is False
    mock_alert.assert_not_called()


def test_price_question_no_alert():
    state = _state(messages=[HumanMessage(content="How much does a root canal cost?")])
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        safety_precheck_node(state)
    mock_alert.assert_not_called()


# ---------------------------------------------------------------------------
# TC-A6: emergency mid-flow — precheck runs on every turn
# ---------------------------------------------------------------------------

def test_emergency_fires_mid_conversation():
    """Alert fires even when patient is mid-booking flow (TC-A6)."""
    state = _state(
        messages=[
            HumanMessage(content="I'd like to book an appointment"),
            HumanMessage(content="Actually my tooth is killing me, severe pain"),
        ],
        active_specialist="booking",
    )
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# Already-emergency state: alert must NOT re-fire
# ---------------------------------------------------------------------------

def test_already_emergency_does_not_re_fire():
    """Once is_emergency is True, subsequent turns skip the alert."""
    state = _state(
        messages=[HumanMessage(content="severe pain")],
        is_emergency=True,
    )
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    mock_alert.assert_not_called()
    # Should not add is_emergency key again (or keep it True)
    assert result.get("is_emergency") is None or result.get("is_emergency") is True


# ---------------------------------------------------------------------------
# Alert payload completeness (partial data is fine — speed over completeness)
# ---------------------------------------------------------------------------

def test_alert_payload_includes_trigger_keyword():
    state = _state(
        messages=[HumanMessage(content="I have severe pain")],
        patient_id="pid-123",
    )
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        safety_precheck_node(state)
    call_kwargs = mock_alert.call_args[0][0]
    assert "trigger_keyword" in call_kwargs
    assert "severe pain" in call_kwargs["trigger_keyword"]


def test_alert_fires_with_no_patient_id():
    """Alert fires even when patient identity is not yet known (TC-A4/A5)."""
    state = _state(
        messages=[HumanMessage(content="dental emergency help")],
        patient_id=None,
    )
    with patch("src.agents.safety_precheck.send_emergency_alert") as mock_alert:
        result = safety_precheck_node(state)
    assert result["is_emergency"] is True
    mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# turn_count always increments
# ---------------------------------------------------------------------------

def test_turn_count_increments_on_every_call():
    state = _state(messages=[HumanMessage(content="hello")], turn_count=3)
    with patch("src.agents.safety_precheck.send_emergency_alert"):
        result = safety_precheck_node(state)
    assert result["turn_count"] == 4


def test_turn_count_increments_even_on_emergency():
    state = _state(messages=[HumanMessage(content="severe pain")], turn_count=1)
    with patch("src.agents.safety_precheck.send_emergency_alert"):
        result = safety_precheck_node(state)
    assert result["turn_count"] == 2
