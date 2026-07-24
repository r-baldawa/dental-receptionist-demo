"""Shared test helpers for Atlas Dental test suite."""
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Supabase chaining helper
# ---------------------------------------------------------------------------

def sb_chain(data=None):
    """Chainable Supabase query mock. All builder methods return self; .execute() returns data."""
    result = MagicMock()
    result.data = data if data is not None else []
    m = MagicMock()
    m.execute.return_value = result
    for attr in ["select", "eq", "neq", "in_", "limit", "order", "insert", "update", "ilike"]:
        getattr(m, attr).return_value = m
    return m


def make_client(responses: dict | None = None):
    """
    Mock Supabase client.

    responses: {table_name: data_list} — client.table(name) returns sb_chain(data).
    Missing table names get an empty chain.
    """
    responses = responses or {}
    client = MagicMock()
    client.table.side_effect = lambda name: sb_chain(responses.get(name, []))
    return client


# ---------------------------------------------------------------------------
# Streamlit stub — must be installed before any import of receivables_view
# ---------------------------------------------------------------------------

def install_streamlit_stub():
    """Install a no-op streamlit mock so Streamlit apps can be imported in tests."""
    if "streamlit" not in sys.modules:
        st = MagicMock()
        st.button.return_value = False
        st.multiselect.return_value = []
        sys.modules["streamlit"] = st
    return sys.modules["streamlit"]
