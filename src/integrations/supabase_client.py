"""
Supabase client — service-role key, backend-only.
Never expose this client or its key to frontend/browser code.
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client


def lookup_patient_by_email_or_phone(
    email: str | None,
    phone: str | None,
) -> dict | None:
    """Return the matching patient row, or None if not found.

    Identity-resolution rules (v3 §2 Step 0):
    - email match → return that record
    - phone-only match → return that record
    - email matches record A, phone matches record B → raise ValueError (flag for human review)
    - no match → return None (new patient path)
    """
    # STUB: Phase 2 queries the `patients` table via supabase client.
    return None
