# Atlas Dental — AI Receptionist

A production-grade AI receptionist for Atlas Dental (Toronto). Built with LangGraph + Claude API, it handles appointment booking, patient registration, dental emergency triage, receivables follow-up, and FAQ — end-to-end, through a Streamlit chat interface.

Try : https://dental-receptionist-ohb5janfxvmtmczcvam6gn.streamlit.app/


---

## What It Does

| Flow | Description |
|---|---|
| **Booking** | New and existing patient appointment booking, PHIPA consent, demographics, insurance, medical/dental history, Google Calendar event, confirmation email |
| **Emergency Triage** | Instant emergency detection (keyword scan before any LLM call), immediate clinic alert, patient-facing guidance, contact info collection and follow-up email |
| **FAQ** | Pricing estimates, clinic hours, services, CDCP questions — sourced only from the clinic knowledge files, never invented |
| **Exceptions** | Identity mismatches, PHIPA declines, anything requiring human review — flagged with full audit log |
| **Receivables** | Staff web app to send individually addressed payment reminder emails to outstanding/overdue patients |

---

## Architecture

```
Patient message
      │
      ▼
┌─────────────────┐
│ Safety Pre-check│  Deterministic keyword scan. No LLM.
│  safety_        │  Emergency detected → alert fires instantly,
│  precheck.py    │  routes to triage, skips manager LLM call.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Manager      │  Claude Haiku. Picks one specialist per turn.
│  manager.py     │
└────────┬────────┘
         │
    ┌────┴──────────────────────────────┐
    ▼           ▼           ▼           ▼
 booking      triage    exceptions     faq
 agent        agent       agent        agent
    │
    └──► END
```

Full detail: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph + MemorySaver) |
| LLM — specialists | Claude Sonnet 4.6 |
| LLM — manager routing | Claude Haiku 4.5 |
| Database | Supabase (Postgres) |
| Email | Gmail SMTP via OAuth2 |
| Calendar | Google Calendar API |
| Chat UI | Streamlit (`app.py`) |
| Receptionist UI | Streamlit (`src/webapp/`) |
| Tests | pytest (77 tests) |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/r-baldawa/Dental-Receptionist.git
cd Dental-Receptionist
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in all required values:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (backend only, never exposed to browser) |
| `GOOGLE_CLIENT_ID` | Google OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 client secret |
| `GOOGLE_REFRESH_TOKEN` | OAuth2 refresh token (for Gmail + Calendar) |
| `GMAIL_SENDER_ADDRESS` | Gmail address used to send emails |
| `GOOGLE_CALENDAR_ID` | Calendar ID for appointment booking |
| `CLINIC_EMERGENCY_ALERT_EMAIL` | Email address that receives emergency alerts |
| `CLINIC_ADMIN_EMAIL` | Email for payment reminders and audit escalations |

### 3. Set up the database

Apply the schema to your Supabase project:

```bash
# Paste schema.sql into the Supabase SQL editor, or use the CLI:
supabase db push  # if using Supabase CLI with local config
```

Tables: `patients`, `appointments`, `consent_records`, `payment_records`, `audit_log`

---

## Running

### Patient-facing chat

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

### Receptionist — Check-in & Consent

```bash
streamlit run src/webapp/consent_view.py
```

Search patients, view pre-filled chat data, sign consent forms in person (tablet).

### Receptionist — Receivables

```bash
streamlit run src/webapp/receivables_view.py
```

View outstanding/overdue balances, send individually addressed payment reminder emails.

### CLI (for testing agent responses directly)

```bash
python cli.py
```

---

## Tests

```bash
pytest
```

77 tests covering safety pre-check, identity resolution, patient data, scheduling idempotency, receivables (PHIPA compliance), knowledge base, and structural non-negotiables.

---

## Non-Negotiables

These are enforced in code, not just in prompts:

| Rule | Enforcement |
|---|---|
| Emergency alert fires on every turn, can't be skipped | `safety_precheck_node` runs before manager on every edge from `START` |
| No agent can trigger or skip an emergency alert | `send_emergency_alert` is not in any agent's tool list |
| Consent signing is in-person only | No `sign_consent` tool exists anywhere in the codebase |
| Payment reminders are one-per-patient | `_send_reminder(record: dict)` accepts one record; no batch signature |
| Identity resolved by DB lookup, not self-report | `lookup_patient_by_contact` called first; "new or returning?" is UX framing only |
| Pricing is always an estimate | `query_pricing_kb` returns pre-formatted strings; never raw numbers |

---

## Project Structure

```
├── app.py                              # Patient-facing Streamlit chat UI
├── cli.py                              # CLI for local testing
├── schema.sql                          # Supabase database schema
├── requirements.txt
├── .env.example                        # Credential template
├── ARCHITECTURE.md                     # Full architecture reference
│
├── atlas_dental_clinic_knowledge.md    # Clinic facts (hours, services, staff)
├── dental_pricing_faq_knowledge_base.json  # Pricing ranges and FAQ
│
├── src/
│   ├── agents/
│   │   ├── runner.py                   # Single external entry point
│   │   ├── safety_precheck.py          # Deterministic emergency scan (no LLM)
│   │   ├── manager.py                  # Haiku router
│   │   ├── booking_agent.py
│   │   ├── triage_agent.py
│   │   ├── exceptions_agent.py
│   │   ├── faq_agent.py
│   │   ├── state.py                    # AtlasDentalState TypedDict
│   │   ├── prompts/                    # Markdown system prompts per agent
│   │   └── tools/                      # LangChain @tool definitions
│   │       ├── consent.py
│   │       ├── emergency.py
│   │       ├── escalation.py
│   │       ├── identity.py
│   │       ├── knowledge.py
│   │       ├── patient_data.py
│   │       └── scheduling.py
│   ├── integrations/
│   │   ├── supabase_client.py
│   │   └── gmail_smtp.py
│   └── webapp/
│       ├── consent_view.py             # Check-in & consent capture (staff)
│       └── receivables_view.py         # Payment follow-up (staff)
│
└── tests/                              # pytest suite (77 tests)
    ├── conftest.py
    ├── test_safety_precheck.py
    ├── test_identity.py
    ├── test_patient_data.py
    ├── test_scheduling.py
    ├── test_receivables.py
    ├── test_knowledge.py
    └── test_non_negotiables.py
```

---

## Knowledge Sources

The agent never has clinic facts hardcoded in prompts. All facts come from two files at query time:

- **`atlas_dental_clinic_knowledge.md`** — hours, address, services, CDCP eligibility, staff, procedures
- **`dental_pricing_faq_knowledge_base.json`** — price ranges per procedure, insurance coverage types, escalation triggers

---

## Security Notes

- `.env` and `client_secret.json` are in `.gitignore` — never commit them
- `SUPABASE_SERVICE_ROLE_KEY` is backend-only; it is never passed to the browser
- PHIPA compliance: one individually addressed email per patient — enforced structurally, not by prompt
# Dental-Receptionist
