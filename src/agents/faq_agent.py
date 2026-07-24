"""
faq_agent.py — pricing and clinic knowledge FAQ specialist.

Phase 5: full tool-calling loop replacing the Phase 1 with_structured_output stub.
Tools: query_pricing_kb, query_clinic_knowledge, flag_for_human_review.

Interrupt-and-return: the manager sets pre_faq_specialist before routing here,
and clears it when routing back. This agent doesn't need to manage that — it just
answers the question and the manager handles the return routing on the next turn.
"""
import json
import os
import pathlib
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.state import AtlasDentalState
from src.agents.tools.escalation import flag_for_human_review
from src.agents.tools.knowledge import query_clinic_knowledge, query_pricing_kb

_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "faq_prompt.md"
_prompt_cache: str | None = None
_llm: Optional[ChatAnthropic] = None

FAQ_TOOLS = [query_pricing_kb, query_clinic_knowledge, flag_for_human_review]
_TOOL_MAP = {t.name: t for t in FAQ_TOOLS}


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


def faq_node(state: AtlasDentalState, config: RunnableConfig | None = None) -> dict:
    llm = _get_llm().bind_tools(FAQ_TOOLS)

    context_note = ""
    pre_faq = state.get("pre_faq_specialist")
    if pre_faq:
        context_note = (
            f"\n\n[System note: Patient interrupted their {pre_faq} flow to ask this question. "
            f"Answer it fully, then offer to continue their booking: "
            f"'Does that help? Happy to continue with your appointment if you're ready.']"
        )

    messages = [SystemMessage(content=_load_prompt() + context_note)] + list(
        state.get("messages") or []
    )

    requires_handoff = False

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

            if tc["name"] == "flag_for_human_review" and result_dict.get("flagged"):
                requires_handoff = True
            # Pricing KB escalation also triggers handoff
            if tc["name"] == "query_pricing_kb" and result_dict.get("escalate"):
                requires_handoff = True

            tool_msgs.append(ToolMessage(content=json.dumps(result_dict), tool_call_id=tc["id"]))
        messages.extend(tool_msgs)

    text = _extract_text(response.content)

    updates: dict = {
        "agent_response": {"text": text},
        "messages": [AIMessage(content=text)],
    }
    if requires_handoff:
        updates["requires_human_handoff"] = True

    return updates
