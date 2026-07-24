"""
safety_precheck.py — deterministic emergency check.

Runs before any LLM call on every single turn, regardless of which specialist
is active. When triggered, calls send_emergency_alert directly as plain code —
this is NOT offered to any agent as a discretionary tool. By the time the manager
or any specialist sees the message, the alert has already fired if it was going to.
See CLAUDE.md non-negotiables and plan.md §3a.
"""
from langchain_core.messages import HumanMessage
from src.agents.state import AtlasDentalState
from src.agents.tools.emergency import send_emergency_alert

_EMERGENCY_KEYWORDS = [
    "severe pain",
    "knocked out",
    "knocked-out",
    "avulsed",
    "can't stop bleeding",
    "cannot stop bleeding",
    "bleeding won't stop",
    "won't stop bleeding",
    "can't breathe",
    "cannot breathe",
    "broken jaw",
    "face swollen",
    "facial swelling",
    "severe swelling",
    "swollen face",
    "trauma",
    "unconscious",
    "difficulty breathing",
    "extreme pain",
    "unbearable pain",
    "abscess",
    "dental emergency",
]


def safety_precheck_node(state: AtlasDentalState) -> dict:
    updates: dict = {"turn_count": (state.get("turn_count") or 0) + 1}

    # Already in emergency — don't re-fire the alert, just let triage stay active
    if state.get("is_emergency"):
        return updates

    # Get the latest human message
    latest = ""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            latest = msg.content.lower()
            break

    for kw in _EMERGENCY_KEYWORDS:
        if kw in latest:
            send_emergency_alert({
                "trigger_keyword": kw,
                "message_snippet": latest[:300],
                "patient_id": state.get("patient_id"),
                "demographics": state.get("demographics") or {},
                "turn": state.get("turn_count") or 0,
                "channel": state.get("channel", "chat"),
            })
            updates["is_emergency"] = True
            updates["escalation_reason"] = f"Emergency keyword detected: '{kw}'"
            # Pre-set specialist so manager doesn't need an LLM call when emergency is obvious
            updates["active_specialist"] = "triage"
            break

    return updates
