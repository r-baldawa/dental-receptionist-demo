"""
runner.py — single external entry point for the Atlas Dental agent.

invoke_agent(message, thread_id) -> {"text": str, "quick_replies": list | None}

External callers (CLI, Streamlit UI, future API) use only this function.
They never call the manager, safety_precheck, or any specialist directly.
"""
import re

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage

# Strips [QR: "A" | "B"] markers from streamed text so they don't appear as raw text in the UI.
_QR_RE = re.compile(r'\s*\[QR:.*?\]', re.DOTALL)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.booking_agent import booking_node
from src.agents.exceptions_agent import exceptions_node
from src.agents.faq_agent import faq_node
from src.agents.manager import manager_node
from src.agents.safety_precheck import safety_precheck_node
from src.agents.state import AtlasDentalState
from src.agents.triage_agent import triage_node

_graph = None


def _route_to_specialist(state: AtlasDentalState) -> str:
    """Read active_specialist set by manager_node. Default to booking if somehow unset."""
    return state.get("active_specialist") or "booking"


def build_graph():
    builder = StateGraph(AtlasDentalState)

    builder.add_node("safety_precheck", safety_precheck_node)
    builder.add_node("manager", manager_node)
    builder.add_node("booking", booking_node)
    builder.add_node("triage", triage_node)
    builder.add_node("exceptions", exceptions_node)
    builder.add_node("faq", faq_node)

    builder.add_edge(START, "safety_precheck")
    builder.add_edge("safety_precheck", "manager")
    builder.add_conditional_edges(
        "manager",
        _route_to_specialist,
        {
            "booking": "booking",
            "triage": "triage",
            "exceptions": "exceptions",
            "faq": "faq",
        },
    )
    for node in ("booking", "triage", "exceptions", "faq"):
        builder.add_edge(node, END)

    return builder.compile(checkpointer=MemorySaver())


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# Human-readable labels for tool calls surfaced live via the status rail (app.py).
# Fallback to a generic label for any tool not listed here.
_TOOL_STEP_LABELS = {
    "lookup_patient_by_contact": "Looking up your file…",
    "create_new_patient": "Setting up your patient record…",
    "update_patient_insurance": "Saving insurance details…",
    "update_medical_history": "Saving medical history…",
    "update_dental_history": "Saving dental history…",
    "update_guardian_info": "Saving guardian details…",
    "get_patient_balance": "Checking your account balance…",
    "get_no_show_history": "Checking appointment history…",
    "record_consent_acknowledgement": "Recording consent…",
    "create_appointment": "Booking your appointment…",
    "book_calendar_event": "Checking calendar availability…",
    "send_appointment_confirmation": "Sending confirmation email…",
    "flag_for_human_review": "Flagging this for staff review…",
    "send_emergency_contact_followup": "Sending your details to our team…",
    "query_pricing_kb": "Looking up pricing…",
    "query_clinic_knowledge": "Checking clinic info…",
}


def stream_agent(message: str, thread_id: str, _meta: dict | None = None):
    """
    Generator that yields ("text", chunk) and ("status", label) tuples.

    ("text", ...) chunks are the user-facing response — accumulate and display these.
    ("status", ...) tuples are transient live-progress labels for tool calls in
    progress (e.g. "Checking calendar availability…") — show, then replace/clear;
    never accumulate them into the displayed text.

    Populates _meta["quick_replies"] and, when a booking is confirmed this turn,
    _meta["summary"] (see booking_agent.py's last_booking_summary) after the stream
    completes.

    Within a booking turn the LLM may run several times (tool-calling loop). We only
    want to show the FINAL user-facing response as text, but tool_use turns are what
    drive the live status rail rather than being silently discarded.
    """
    from langchain_core.messages import AIMessageChunk

    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    token_stream_nodes = {"booking", "triage", "exceptions"}
    faq_text: str | None = None
    chunk_buffer: list = []
    merged_chunk = None
    had_confirmation_before = bool(
        (graph.get_state(config).values or {}).get("confirmation_email_sent")
    )

    def _extract_text_from_chunk(c) -> str:
        content = c.content if hasattr(c, "content") else ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    parts.append(block["text"])
            return "".join(parts)
        return ""

    for event in graph.stream(
        {"messages": [HumanMessage(content=message)], "channel": "chat"},
        config,
        stream_mode=["messages", "updates"],
    ):
        kind, data = event
        if kind == "messages":
            chunk, metadata = data
            # Skip complete AIMessage state-update objects — only process streaming chunks
            if not isinstance(chunk, AIMessageChunk):
                continue
            if metadata.get("langgraph_node") not in token_stream_nodes:
                continue

            chunk_buffer.append(chunk)
            merged_chunk = merged_chunk + chunk if merged_chunk is not None else chunk

            stop_reason = (chunk.response_metadata or {}).get("stop_reason")
            if stop_reason == "end_turn":
                # Join all chunks, strip any [QR: ...] markers so they don't
                # appear as raw text — quick_replies arrive via the updates event.
                full = "".join(_extract_text_from_chunk(c) for c in chunk_buffer)
                clean = _QR_RE.sub("", full).strip()
                if clean:
                    yield ("text", clean)
                chunk_buffer.clear()
                merged_chunk = None
            elif stop_reason == "tool_use":
                # Intermediate call — surface a live status label instead of the
                # (usually empty/partial) text, then discard the text buffer.
                for tc in (merged_chunk.tool_calls or []) if merged_chunk else []:
                    label = _TOOL_STEP_LABELS.get(tc["name"], "Working on it…")
                    yield ("status", label)
                chunk_buffer.clear()
                merged_chunk = None
            elif stop_reason:
                chunk_buffer.clear()
                merged_chunk = None

        elif kind == "updates":
            for node, updates in data.items():
                if not isinstance(updates, dict):
                    continue
                resp = updates.get("agent_response") or {}
                if node == "faq" and resp.get("text"):
                    faq_text = resp["text"]
                if _meta is not None and resp.get("quick_replies"):
                    _meta["quick_replies"] = resp["quick_replies"]

    if faq_text:
        yield ("text", faq_text)

    if _meta is not None:
        final_state = graph.get_state(config).values or {}
        confirmed_now = bool(final_state.get("confirmation_email_sent"))
        if confirmed_now and not had_confirmation_before:
            summary = final_state.get("last_booking_summary")
            if summary:
                _meta["summary"] = summary


def invoke_agent(message: str, thread_id: str) -> dict:
    """
    Process one patient turn. Returns {"text": str, "quick_replies": list | None}.

    State persists across calls with the same thread_id via MemorySaver.
    The full conversation history (messages) is maintained automatically.
    """
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    result = graph.invoke(
        {"messages": [HumanMessage(content=message)], "channel": "chat"},
        config,
    )

    raw = result.get("agent_response") or {}
    return {
        "text": raw.get("text") or "I'm sorry, something went wrong. Please try again.",
        "quick_replies": raw.get("quick_replies"),
    }
