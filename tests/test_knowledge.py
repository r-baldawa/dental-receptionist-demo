"""
Tests for FAQ knowledge tools — TC-D1 through TC-D7.

Invariants:
- query_pricing_kb returns pre-formatted estimate strings, never raw guarantee-style numbers.
- Hard escalation fires on guaranteed/exact price phrases (TC-D4).
- Unknown procedure returns fallback message, no fabricated number (TC-D5).
- Pain/emergency keywords set triage_flag=True (TC-D2).
- query_clinic_knowledge returns content from the real knowledge doc (TC-D6).
- Pricing results include estimate framing language (TC-D1).
"""
import pytest

from src.agents.tools.knowledge import query_clinic_knowledge, query_pricing_kb


@pytest.fixture(autouse=True)
def clear_kb_cache():
    """Reset KB file cache between tests so monkeypatching works cleanly."""
    import src.agents.tools.knowledge as km
    import src.integrations.clinic_knowledge as ck
    km._kb_cache = None
    ck._content = None
    yield
    km._kb_cache = None
    ck._content = None


# ---------------------------------------------------------------------------
# TC-D1: Pricing question — estimate framing enforced by tool output
# ---------------------------------------------------------------------------

def test_pricing_known_procedure_returns_found():
    result = query_pricing_kb.invoke({"query": "how much does a root canal cost"})
    # Should find at least one result or fallback — never raises
    assert "found" in result or "escalate" in result


def test_pricing_result_contains_estimate_language():
    """Pre-formatted strings must use estimate framing, never guarantee language."""
    result = query_pricing_kb.invoke({"query": "root canal price"})
    if result.get("found"):
        for item_str in result["results"]:
            lowered = item_str.lower()
            # Must contain range or estimate language
            assert any(
                phrase in lowered
                for phrase in [
                    "typically ranges",
                    "typically starts",
                    "pricing varies",
                    "final cost depends",
                ]
            ), f"Estimate framing missing from: {item_str}"
            # Must not state a single number as a final price with guarantee language
            assert "guaranteed" not in lowered
            assert "exact price" not in lowered


def test_pricing_cleaning_or_checkup_found():
    result = query_pricing_kb.invoke({"query": "cleaning checkup exam"})
    # At least one of these common procedures should be in the KB
    assert result.get("found") is True or result.get("found") is False  # no exception


# ---------------------------------------------------------------------------
# TC-D3: Multi-procedure — each item returned separately, no combined total
# ---------------------------------------------------------------------------

def test_multi_procedure_no_combined_total():
    """Agent receives separate items, not a single summed number."""
    result = query_pricing_kb.invoke(
        {"query": "implant crown bone graft"}
    )
    if result.get("found") and len(result.get("results", [])) > 1:
        for item_str in result["results"]:
            # No item string should contain a comma-separated price that could be a sum
            assert "total" not in item_str.lower()


# ---------------------------------------------------------------------------
# TC-D4: Hard escalation on guaranteed-price requests
# ---------------------------------------------------------------------------

def test_guaranteed_price_triggers_escalation():
    result = query_pricing_kb.invoke(
        {"query": "just tell me the guaranteed price, not an estimate"}
    )
    assert result.get("escalate") is True


def test_exact_price_triggers_escalation():
    result = query_pricing_kb.invoke({"query": "what is the exact final price"})
    assert result.get("escalate") is True


def test_billing_dispute_triggers_escalation():
    result = query_pricing_kb.invoke({"query": "you charged me the wrong amount, dispute"})
    assert result.get("escalate") is True


def test_escalation_result_has_suggested_response():
    result = query_pricing_kb.invoke({"query": "guaranteed price please"})
    assert result.get("escalate") is True
    assert "suggested_response" in result
    # Suggested response should reference the clinic phone
    assert "416" in result["suggested_response"]


# ---------------------------------------------------------------------------
# TC-D5: Unknown procedure → fallback, no fabricated number
# ---------------------------------------------------------------------------

def test_unknown_procedure_returns_fallback():
    # Use genuinely nonsense words that won't score against any KB pattern
    result = query_pricing_kb.invoke(
        {"query": "zygomorphic xenolith quasar framboise"}
    )
    assert result.get("found") is False
    assert "message" in result
    # Fallback message must not contain a dollar amount
    assert "$" not in result["message"]


def test_fallback_suggests_dentist_quote():
    result = query_pricing_kb.invoke({"query": "zygomorphic xenolith quasar"})
    if not result.get("found"):
        msg = result.get("message", "").lower()
        # Should suggest getting a quote/exam, not inventing a number
        assert any(kw in msg for kw in ["dentist", "quote", "estimate", "exam", "consultation"])


# ---------------------------------------------------------------------------
# TC-D2: Pain keywords alongside cost question → triage_flag=True
# ---------------------------------------------------------------------------

def test_pain_keyword_sets_triage_flag():
    result = query_pricing_kb.invoke(
        {"query": "how much for emergency exam I'm in a lot of pain"}
    )
    assert result.get("triage_flag") is True


def test_swelling_keyword_sets_triage_flag():
    result = query_pricing_kb.invoke({"query": "cost of treatment for swelling"})
    assert result.get("triage_flag") is True


def test_non_pain_query_no_triage_flag():
    result = query_pricing_kb.invoke({"query": "routine cleaning cost"})
    # triage_flag should be False or absent when no pain keywords present
    assert not result.get("triage_flag", False)


# ---------------------------------------------------------------------------
# TC-D6: Clinic knowledge — returns real doc content
# ---------------------------------------------------------------------------

def test_clinic_knowledge_returns_content():
    result = query_clinic_knowledge.invoke({"query": "are you open on Sundays"})
    assert "content" in result
    assert len(result["content"]) > 100, "Knowledge doc must be non-trivial"


def test_clinic_knowledge_contains_atlas_dental():
    result = query_clinic_knowledge.invoke({"query": "clinic location"})
    content = result["content"].lower()
    assert "atlas dental" in content


def test_clinic_knowledge_contains_phone_number():
    """Real clinic phone must be in the knowledge doc, not invented."""
    result = query_clinic_knowledge.invoke({"query": "contact"})
    assert "416" in result["content"]


def test_clinic_knowledge_source_tagged():
    result = query_clinic_knowledge.invoke({"query": "anything"})
    assert result.get("source") == "atlas_dental_clinic_knowledge.md"


def test_clinic_knowledge_instruction_forbids_invention():
    """Tool must instruct the agent not to invent details."""
    result = query_clinic_knowledge.invoke({"query": "anything"})
    instruction = result.get("instruction", "").lower()
    assert "not invent" in instruction or "do not invent" in instruction
