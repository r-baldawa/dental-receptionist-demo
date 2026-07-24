"""
manager.py — intent classification and specialist routing.

Uses an LLM call (structured output) to decide which specialist handles each turn.
Skips the LLM call when routing is already determined by state (emergency, handoff).
"""
import os
import pathlib
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.agents.state import AtlasDentalState


class RouteDecision(BaseModel):
    specialist: Literal["booking", "triage", "exceptions", "faq"]
    reasoning: str = Field(description="One-sentence reason for this routing decision")


_PROMPT_PATH = pathlib.Path(__file__).parent / "prompts" / "manager_prompt.md"
_prompt_cache: str | None = None

_llm = None


def _load_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = _PROMPT_PATH.read_text()
    return _prompt_cache


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        model = os.getenv("MANAGER_MODEL", "claude-haiku-4-5-20251001")
        _llm = ChatAnthropic(model=model, temperature=0)
    return _llm


def manager_node(state: AtlasDentalState) -> dict:
    """
    Classify intent and set active_specialist.
    No LLM call when routing can be decided from state alone.
    """
    # Emergency pre-empts everything — precheck already set active_specialist="triage"
    if state.get("is_emergency"):
        return {"active_specialist": "triage"}

    # Human handoff decided — keep specialist, don't reclassify
    if state.get("requires_human_handoff"):
        return {"active_specialist": state.get("active_specialist") or "exceptions"}

    # LLM classification
    pre_faq = state.get("pre_faq_specialist")
    state_context = (
        f"\n\n## Current State\n"
        f"- active_specialist: {state.get('active_specialist') or 'none (first turn)'}\n"
        f"- pre_faq_specialist: {pre_faq or 'none'}\n"
        f"- patient_type: {state.get('patient_type') or 'not yet determined'}\n"
        f"- identity_confirmed: {state.get('identity_confirmed')}\n"
        f"- identity_mismatch: {state.get('identity_mismatch', False)}\n"
        f"- consent_given: {state.get('consent_given')}\n"
        f"- requires_human_handoff: {state.get('requires_human_handoff', False)}\n"
    )
    if pre_faq:
        state_context += (
            f"\n[Interrupt-and-return: the patient interrupted their {pre_faq} flow to ask a FAQ "
            f"question. If the current message is NOT another FAQ/pricing/clinic question, "
            f"route back to '{pre_faq}' so their booking continues from where it left off.]\n"
        )

    structured = _get_llm().with_structured_output(RouteDecision)
    messages = [SystemMessage(content=_load_prompt() + state_context)] + list(
        state.get("messages") or []
    )

    result = structured.invoke(messages)
    updates: dict = {"active_specialist": result.specialist}

    # Save pre_faq_specialist when interrupting into FAQ from another specialist
    if result.specialist == "faq" and state.get("active_specialist") not in (None, "faq"):
        updates["pre_faq_specialist"] = state.get("active_specialist")
    # Clear pre_faq_specialist when returning from FAQ to another specialist
    elif result.specialist != "faq" and pre_faq:
        updates["pre_faq_specialist"] = None

    return updates
