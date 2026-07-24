from typing import Annotated, Optional, Literal
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AtlasDentalState(TypedDict):
    # Conversation history — add_messages reducer appends, never replaces
    messages: Annotated[list[BaseMessage], add_messages]
    channel: str
    turn_count: int

    # Routing — which specialist is currently handling the conversation
    active_specialist: Optional[Literal["booking", "triage", "exceptions", "faq"]]
    # Interrupt-and-return: specialist to resume after the FAQ agent answers
    pre_faq_specialist: Optional[str]

    # Emergency state — set by safety_precheck, never by an agent
    is_emergency: bool
    escalation_reason: Optional[str]

    # Patient identity
    patient_id: Optional[str]
    patient_type: Optional[Literal["new", "existing"]]
    identity_confirmed: Optional[bool]
    identity_mismatch: bool

    # Registration data collected conversationally (written to DB via tools in Phase 2)
    consent_given: Optional[bool]
    demographics: dict
    insurance: dict
    medical_history: dict
    dental_history: dict
    is_minor: bool
    guardian_info: Optional[dict]

    # Booking side effects (idempotency guards per design doc)
    scheduling: dict
    calendar_event_id: Optional[str]
    confirmation_email_sent: bool
    # Set the same turn confirmation_email_sent flips to True; used to render
    # a structured confirmation card. Not cleared afterward — runner.py detects
    # the False->True transition rather than relying on absence/presence.
    last_booking_summary: Optional[dict]

    # Human handoff
    requires_human_handoff: bool

    # Output — the structured response for this turn
    agent_response: Optional[dict]  # {"text": str, "quick_replies": list | None}
