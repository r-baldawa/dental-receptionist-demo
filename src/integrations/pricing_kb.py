"""
Pricing knowledge base — exact-intent match against dental_pricing_faq_knowledge_base.json.
Phase 5 wires the real intent-matching logic.
"""
import json
from pathlib import Path

_KB_PATH = Path(__file__).parent.parent.parent / "dental_pricing_faq_knowledge_base.json"
_kb: list | None = None


def _load() -> list:
    global _kb
    if _kb is None:
        with open(_KB_PATH, encoding="utf-8") as f:
            _kb = json.load(f)
    return _kb


def lookup_pricing(user_query: str) -> dict | None:
    """Return the matching KB entry or None.

    Phase 5 will match user_query against each entry's question_patterns array.
    Hard escalation triggers (guaranteed-price ask, billing dispute, etc.) are
    embedded in each entry's escalate_to_human_if list — the caller must check
    those even when a match is found.
    """
    # STUB: Phase 5 implements intent matching.
    return None


def get_fallback_response() -> str:
    """Return the KB's built-in fallback for queries not matched to any entry."""
    # STUB: Phase 5 reads the fallback from the KB JSON.
    return (
        "I don't have a precise estimate for that procedure on hand. "
        "I'd recommend booking a consultation — our dentist can give you an accurate quote "
        "after an in-person assessment."
    )
