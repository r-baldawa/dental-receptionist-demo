"""
Knowledge tools for the FAQ agent — Phase 5 implementation.

query_pricing_kb  — keyword-matches against the pricing JSON, returns pre-formatted
                    estimate-range strings (never raw numbers). Hard escalation signals
                    are returned when the KB's escalate_to_human_if triggers fire.

query_clinic_knowledge — returns the full Atlas Dental clinic knowledge doc.

Per plan.md §3a: query_pricing_kb returns pre-formatted strings, not raw numbers,
so the FAQ agent structurally cannot state a price as a guaranteed final cost.
"""
import json
from pathlib import Path

from langchain_core.tools import tool

from src.integrations.clinic_knowledge import get_clinic_knowledge

_KB_PATH = Path(__file__).parent.parent.parent.parent / "dental_pricing_faq_knowledge_base.json"
_kb_cache: dict | None = None

_ESCALATE_PHRASES = [
    "guaranteed price", "exact price", "final price", "exact cost", "final cost",
    "guarantee", "promise me", "tell me exactly", "dispute", "billing dispute",
    "quoted me", "charged me", "treatment plan",
]


def _get_kb() -> dict:
    global _kb_cache
    if _kb_cache is None:
        _kb_cache = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    return _kb_cache


def _format_item(item: dict) -> str:
    """Return a pre-formatted estimate string — never a single final guaranteed number."""
    pr = item.get("price_range", {})
    low = pr.get("low")
    high = pr.get("high")
    note = pr.get("note", "")
    name = item.get("id", "").replace("_", " ").title()

    if low and high:
        price_str = f"typically ranges from ${low:,} to ${high:,} CAD"
    elif low:
        price_str = f"typically starts around ${low:,} CAD"
    else:
        price_str = "pricing varies by case"

    note_part = f" ({note})" if note else ""
    coverage = item.get("insurance_coverage", "")
    coverage_part = f" Commonly considered {coverage} under most dental plans." if coverage else ""
    cosmetic = item.get("cosmetic", False)
    cosmetic_part = " Note: cosmetic procedures are typically not covered by insurance." if cosmetic else ""

    return (
        f"**{name}**: {price_str}{note_part}.{coverage_part}{cosmetic_part} "
        f"Final cost depends on the dentist's in-person assessment and case complexity."
    )


@tool
def query_pricing_kb(query: str) -> dict:
    """Search the Atlas Dental pricing knowledge base for procedure cost estimates.

    Returns pre-formatted estimate-range strings. Never returns a raw number as a
    guaranteed final price — the output format enforces estimate framing by design.

    Returns escalate=True when:
    - Patient demands a guaranteed/exact final price
    - Patient disputes a quoted price or past bill
    - Query involves a complex multi-procedure treatment plan

    Args:
        query: The patient's pricing question in natural language
    """
    kb = _get_kb()
    query_lower = query.lower()

    # Escalation check before any pricing lookup
    if any(phrase in query_lower for phrase in _ESCALATE_PHRASES):
        return {
            "escalate": True,
            "reason": "Patient requesting guaranteed/exact price or disputing a charge.",
            "escalate_triggers": kb.get("escalate_to_human_if", []),
            "suggested_response": (
                "That's something I'd need to connect you with a team member for — "
                "they can give you accurate details. "
                "You're welcome to call us at 416-597-0534 or I can arrange a callback."
            ),
        }

    # Triage flag — pain/trauma alongside a cost question
    triage_keywords = ["pain", "swelling", "trauma", "bleeding", "emergency", "urgent", "hurts", "killing me"]
    triage_flag = any(kw in query_lower for kw in triage_keywords)

    # Keyword-score each KB item
    scored: list[tuple[int, dict]] = []
    for item in kb.get("faq_items", []):
        combined = (
            " ".join(item.get("question_patterns", [])) + " "
            + item.get("id", "").replace("_", " ") + " "
            + item.get("category", "")
        ).lower()
        score = sum(1 for word in query_lower.split() if len(word) > 3 and word in combined)
        if score > 0:
            scored.append((score, item))

    if not scored:
        return {
            "found": False,
            "triage_flag": triage_flag,
            "message": kb.get(
                "fallback_response",
                "I don't have specific pricing for that procedure. "
                "The dentist can give you a personalized quote after an exam.",
            ),
        }

    max_score = max(s for s, _ in scored)
    top_items = [item for score, item in scored if score >= max_score]

    return {
        "found": True,
        "results": [_format_item(item) for item in top_items],
        "triage_flag": triage_flag or any(item.get("triage_flag") for item in top_items),
        "behavior_rules": kb.get("agent_behavior_rules", [])[:3],
    }


@tool
def query_clinic_knowledge(query: str) -> dict:
    """Look up Atlas Dental clinic information: hours, location, services, CDCP, parking, etc.

    Use for any non-pricing questions about the clinic: opening hours, address,
    accepted insurance programs, accessibility, available services, and similar.
    Answer only from the returned content — never invent clinic details.

    Args:
        query: The patient's question about the clinic
    """
    return {
        "content": get_clinic_knowledge(),
        "source": "atlas_dental_clinic_knowledge.md",
        "instruction": "Answer only from the content above. Do not invent details not present.",
    }
