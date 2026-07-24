"""
booking_agent.py — booking specialist for new and existing patients.
Full tool-calling loop: identity lookup → DB writes → calendar → email.
"""
import json
import os
import pathlib
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from src.agents.state import AtlasDentalState
from src.agents.tools.identity import lookup_patient_by_contact
from src.agents.tools.patient_data import (
    create_new_patient,
    get_no_show_history,
    get_patient_balance,
    update_dental_history,
    update_guardian_info,
    update_medical_history,
    update_patient_insurance,
)
from src.agents.tools.scheduling import (
    book_calendar_event,
    create_appointment,
    send_appointment_confirmation,
)
from src.agents.tools.escalation import flag_for_human_review
from src.agents.tools.consent import record_consent_acknowledgement
from src.integrations.clinic_knowledge import get_clinic_knowledge
from src.integrations.clock import get_current_context_line

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "booking_prompt.md"
_prompt_cache: Optional[str] = None
_llm: Optional[ChatAnthropic] = None

BOOKING_TOOLS: list[BaseTool] = [
    lookup_patient_by_contact,
    create_new_patient,
    update_patient_insurance,
    update_medical_history,
    update_dental_history,
    update_guardian_info,
    get_patient_balance,
    get_no_show_history,
    record_consent_acknowledgement,
    create_appointment,
    book_calendar_event,
    send_appointment_confirmation,
    flag_for_human_review,
]

_TOOL_MAP = {t.name: t for t in BOOKING_TOOLS}


def _load_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        base = _PROMPT_PATH.read_text()
        _prompt_cache = f"{base}\n\n---\n\n## Clinic Knowledge (Atlas Dental)\n\n{get_clinic_knowledge()}"
    return _prompt_cache


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        _llm = ChatAnthropic(model=model, temperature=0.3)
    return _llm


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif hasattr(block, "type") and block.type == "text":
                parts.append(getattr(block, "text", ""))
        return " ".join(p for p in parts if p)
    return str(content)


def _build_context_note(state: AtlasDentalState) -> str:
    """Inject a system note so the agent knows where it is mid-conversation.

    Without this, the agent re-runs Step 0 (identity lookup) every turn because it sees
    the patient's email in the message history and calls lookup_patient_by_contact again.
    """
    patient_id = state.get("patient_id")
    if not patient_id:
        return ""

    parts = [
        "[System context — do NOT re-run identity resolution or re-introduce yourself.]",
        f"Patient already identified: patient_id={patient_id}, type={state.get('patient_type', 'unknown')}.",
    ]

    if state.get("confirmation_email_sent"):
        parts.append("Appointment confirmed and confirmation email sent.")
    elif state.get("calendar_event_id"):
        parts.append("Calendar event created; confirmation email not yet sent.")

    if state.get("requires_human_handoff"):
        parts.append("Human handoff already flagged — do not re-flag.")

    parts.append("Continue the conversation from where it left off.")
    return "\n".join(parts)


def booking_node(state: AtlasDentalState, config: RunnableConfig | None = None) -> dict:
    llm = _get_llm().bind_tools(BOOKING_TOOLS)

    system_content = _load_prompt() + "\n\n---\n\n" + get_current_context_line()
    context_note = _build_context_note(state)
    if context_note:
        system_content = system_content + "\n\n---\n\n" + context_note

    messages = [SystemMessage(content=system_content)] + list(state.get("messages") or [])

    # Track tool results for state extraction after the loop
    tool_results_log: list[tuple[str, dict]] = []

    # Tool-calling loop: run until LLM produces a plain text response
    while True:
        response = llm.invoke(messages, config)
        messages.append(response)

        if not response.tool_calls:
            break

        tool_msgs = []
        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            if tool_fn:
                result = tool_fn.invoke(tc["args"])
            else:
                result = {"error": f"Unknown tool: {tc['name']}"}

            # Normalise to dict for logging and serialisation
            result_dict = result if isinstance(result, dict) else {"result": str(result)}
            tool_results_log.append((tc["name"], result_dict))
            tool_msgs.append(
                ToolMessage(
                    content=json.dumps(result_dict),
                    tool_call_id=tc["id"],
                )
            )
        messages.extend(tool_msgs)

    # Extract state updates from tool results
    state_delta: dict = {}
    for tool_name, result in tool_results_log:
        if tool_name == "lookup_patient_by_contact":
            if result.get("conflict"):
                state_delta["identity_mismatch"] = True
            elif result.get("found"):
                state_delta["patient_id"] = result["patient"]["patient_id"]
                state_delta["patient_type"] = "existing"
                state_delta["identity_confirmed"] = False  # still needs name+DOB confirm
            else:
                state_delta["patient_type"] = "new"

        elif tool_name == "create_new_patient" and result.get("success"):
            state_delta["patient_id"] = result["patient_id"]
            state_delta["patient_type"] = "new"

        elif tool_name == "book_calendar_event" and result.get("success"):
            state_delta["calendar_event_id"] = result.get("event_id")

        elif tool_name == "send_appointment_confirmation" and result.get("success"):
            state_delta["confirmation_email_sent"] = True

        elif tool_name == "flag_for_human_review":
            state_delta["requires_human_handoff"] = True

    text = _extract_text(response.content)

    return {
        **state_delta,
        "agent_response": {"text": text},
        "messages": [AIMessage(content=text)],
    }
