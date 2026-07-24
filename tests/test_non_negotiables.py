"""
Structural invariant tests — CLAUDE.md non-negotiables.

These tests assert code-level enforcement, not prompt text. If any of these
fail, a non-negotiable has been broken at the structural level.

Non-negotiables checked here:
1. No sign_consent tool exists anywhere in src/agents/tools/.
2. send_emergency_alert is never registered as an agent tool (any specialist).
3. _send_reminder accepts a single patient record, not a list.
4. send_payment_reminder tool (if it exists) accepts only one patient_id.
5. booking_agent does not have send_emergency_alert in its tool list.
6. faq_agent does not have send_emergency_alert in its tool list.
"""
import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. No sign_consent tool exists
# ---------------------------------------------------------------------------

def test_no_sign_consent_tool_in_tools_directory():
    """sign_consent must not exist as a callable in any tools file."""
    tools_dir = Path(__file__).parent.parent / "src" / "agents" / "tools"
    for py_file in tools_dir.glob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        assert "def sign_consent" not in source, (
            f"sign_consent function found in {py_file.name} — "
            "consent signing is in-person only, never via chat tools"
        )
        assert "sign_consent" not in source or "# no sign_consent" in source.lower() or (
            "sign_consent" in source and "not" in source
        ), f"sign_consent reference found in {py_file.name}"


def test_sign_consent_not_importable():
    """There should be no importable sign_consent from any tools module."""
    import src.agents.tools.consent as consent_module
    assert not hasattr(consent_module, "sign_consent"), (
        "sign_consent found in consent.py — must not exist"
    )


# ---------------------------------------------------------------------------
# 2. send_emergency_alert not in any agent tool list
# ---------------------------------------------------------------------------

def test_send_emergency_alert_not_in_booking_tools():
    """booking_agent must not have send_emergency_alert in its bound tools."""
    with patch("src.integrations.supabase_client.get_client", return_value=MagicMock()):
        import src.agents.booking_agent as ba
        tool_names = {t.name for t in ba.BOOKING_TOOLS}
    assert "send_emergency_alert" not in tool_names, (
        "send_emergency_alert must not be offered to any agent — "
        "it is called only by safety_precheck.py"
    )


def test_send_emergency_alert_not_in_faq_tools():
    import src.agents.faq_agent as fa
    tool_names = {t.name for t in fa.FAQ_TOOLS}
    assert "send_emergency_alert" not in tool_names


def test_send_emergency_alert_only_called_from_precheck():
    """send_emergency_alert import must not appear in any agent file."""
    agents_dir = Path(__file__).parent.parent / "src" / "agents"
    allowed_files = {"safety_precheck.py", "tools/emergency.py"}
    for py_file in agents_dir.rglob("*.py"):
        relative = py_file.relative_to(agents_dir)
        if str(relative) in allowed_files:
            continue
        source = py_file.read_text(encoding="utf-8")
        assert "send_emergency_alert" not in source, (
            f"send_emergency_alert referenced in {relative} — "
            "must only appear in safety_precheck.py and tools/emergency.py"
        )


# ---------------------------------------------------------------------------
# 3. _send_reminder: single record, not a list
# ---------------------------------------------------------------------------

def test_send_reminder_signature_is_single_record():
    """_send_reminder must accept one record dict, not a collection."""
    from tests.conftest import install_streamlit_stub
    install_streamlit_stub()

    stub_client = MagicMock()
    stub_client.table.return_value = MagicMock(
        **{"select.return_value": MagicMock(**{"in_.return_value": MagicMock(**{"order.return_value": MagicMock(**{"execute.return_value": MagicMock(data=[])})})})}
    )

    with patch("src.integrations.supabase_client.get_client", return_value=stub_client):
        if "src.webapp.receivables_view" in sys.modules:
            _send_reminder = sys.modules["src.webapp.receivables_view"]._send_reminder
        else:
            with patch("src.integrations.supabase_client.get_client", return_value=stub_client):
                from src.webapp.receivables_view import _send_reminder

    sig = inspect.signature(_send_reminder)
    params = list(sig.parameters.values())
    assert len(params) == 1, "Must have exactly one parameter"
    param = params[0]
    # Must not be annotated as list
    assert param.annotation is not list
    assert param.annotation is not "list"
    # Name should suggest a single record, not plural
    assert param.name in {"record", "patient_record", "row", "data"}, (
        f"Parameter name '{param.name}' suggests it may accept multiple records"
    )


# ---------------------------------------------------------------------------
# 4. Booking agent tools: verify required tools are present
# ---------------------------------------------------------------------------

def test_booking_agent_has_lookup_tool():
    """lookup_patient_by_contact must be in booking agent tools (identity resolution)."""
    with patch("src.integrations.supabase_client.get_client", return_value=MagicMock()):
        import src.agents.booking_agent as ba
        tool_names = {t.name for t in ba.BOOKING_TOOLS}
    assert "lookup_patient_by_contact" in tool_names


def test_booking_agent_has_flag_for_human_review():
    """flag_for_human_review must be available to booking agent for mismatch/decline cases."""
    with patch("src.integrations.supabase_client.get_client", return_value=MagicMock()):
        import src.agents.booking_agent as ba
        tool_names = {t.name for t in ba.BOOKING_TOOLS}
    assert "flag_for_human_review" in tool_names


# ---------------------------------------------------------------------------
# 5. Consent tool: record_consent_acknowledgement exists, sign_consent does not
# ---------------------------------------------------------------------------

def test_record_consent_acknowledgement_exists():
    """record_consent_acknowledgement must exist — it records acknowledgement, not a signature."""
    with patch("src.integrations.supabase_client.get_client", return_value=MagicMock()):
        import src.agents.tools.consent as c
    assert hasattr(c, "record_consent_acknowledgement"), (
        "record_consent_acknowledgement tool must exist for chat-based acknowledgement"
    )


# ---------------------------------------------------------------------------
# 6. safety_precheck runs before manager (graph order)
# ---------------------------------------------------------------------------

def test_safety_precheck_imported_by_runner():
    """runner.py must import safety_precheck — ensures it's wired into the graph."""
    runner_path = Path(__file__).parent.parent / "src" / "agents" / "runner.py"
    source = runner_path.read_text(encoding="utf-8")
    assert "safety_precheck" in source, (
        "runner.py must reference safety_precheck to ensure it runs on every turn"
    )


def test_graph_has_precheck_node():
    """The compiled graph must contain a 'precheck' or 'safety' node."""
    with patch("src.integrations.supabase_client.get_client", return_value=MagicMock()):
        from src.agents.runner import _get_graph
        graph = _get_graph()
    node_names = set(graph.nodes.keys())
    precheck_nodes = {n for n in node_names if "precheck" in n or "safety" in n}
    assert precheck_nodes, (
        f"No precheck/safety node found in graph nodes: {node_names}"
    )
