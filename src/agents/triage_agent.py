"""
triage_agent.py — emergency follow-up specialist.

The emergency alert has already fired in safety_precheck.py before this agent runs.
This agent handles the patient-facing follow-up: calm reassurance, severity assessment,
ER guidance when needed, contact info collection, and audit logging.
"""
import json
import os
import pathlib
import re
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.state import AtlasDentalState
from src.agents.tools.emergency import send_emergency_contact_followup
from src.agents.tools.escalation import flag_for_human_review
from src.integrations.clock import get_current_context_line

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "triage_prompt.md"
_prompt_cache: str | None = None
_llm: Optional[ChatAnthropic] = None

TRIAGE_TOOLS = [send_emergency_contact_followup, flag_for_human_review]
_TOOL_MAP = {t.name: t for t in TRIAGE_TOOLS}

# Matches [QR: "Option A" | "Option B" | ...] anywhere in the text.
_QR_RE = re.compile(r'\[QR:\s*(.*?)\]', re.DOTALL)


def _load_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text()
    return _prompt_cache


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        _llm = ChatAnthropic(model=model, temperature=0.2)
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


def _parse_quick_replies(text: str) -> tuple[str, list[str]]:
    """Extract [QR: "A" | "B"] markers from text.

    Returns (clean_text, quick_replies_list). The marker is stripped from the
    displayed text so patients only see the buttons, not the raw tag.
    """
    match = _QR_RE.search(text)
    if not match:
        return text, []

    raw = match.group(1)
    options = [opt.strip().strip('"').strip("'") for opt in raw.split("|")]
    options = [o for o in options if o]
    clean = _QR_RE.sub("", text).strip()
    return clean, options


def triage_node(state: AtlasDentalState, config: RunnableConfig | None = None) -> dict:
    llm = _get_llm().bind_tools(TRIAGE_TOOLS)

    escalation_note = ""
    if state.get("escalation_reason"):
        escalation_note = (
            f"\n\n[System note: Emergency triggered by: {state['escalation_reason']}. "
            "Alert already sent to clinic.]"
        )

    system_content = _load_prompt() + "\n\n---\n\n" + get_current_context_line() + escalation_note
    messages = [SystemMessage(content=system_content)] + list(
        state.get("messages") or []
    )

    while True:
        response = llm.invoke(messages, config)
        messages.append(response)

        if not response.tool_calls:
            break

        tool_msgs = []
        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            result = tool_fn.invoke(tc["args"]) if tool_fn else {"error": f"Unknown tool: {tc['name']}"}
            result_dict = result if isinstance(result, dict) else {"result": str(result)}
            tool_msgs.append(ToolMessage(content=json.dumps(result_dict), tool_call_id=tc["id"]))
        messages.extend(tool_msgs)

    raw_text = _extract_text(response.content)
    text, quick_replies = _parse_quick_replies(raw_text)

    return {
        "agent_response": {"text": text, "quick_replies": quick_replies or None},
        "messages": [AIMessage(content=text)],
        "requires_human_handoff": True,
    }
