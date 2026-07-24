# Atlas Dental — AI Receptionist

A production-grade AI receptionist for Atlas Dental (Toronto). Built with LangGraph + Claude API, it handles appointment booking, patient registration, dental emergency triage, receivables follow-up, and FAQ — end-to-end, through a Streamlit chat interface.

**Live demo:** https://dental-receptionist-demo.streamlit.app/ — reach out to r.baldawa17@gmail.com for the access passcode.

---

## Why This Exists

A dental front desk spends a large share of its day on a small set of repetitive, structured conversations: booking, intake paperwork, "what does this cost," and triaging urgent calls. Those conversations are high-volume but low-ambiguity — which makes them a good fit for an agent, provided the risky parts (consent, emergencies, billing communication) are handled by rules a model can't talk itself out of, not by a prompt hoping the model stays disciplined over a long conversation.

That's the design bet this project makes: **non-negotiables live in code, not prompts.** An LLM picks the words; it never gets to decide whether an emergency alert fires, whether a consent form counts as signed, or whether a payment reminder goes to more than one patient at a time. See [Non-Negotiables](#non-negotiables) below for exactly how that's enforced.

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
| Chat UI | Streamlit (`app.py`) — live per-step status updates, structured booking confirmation cards |
| Receptionist UI | Streamlit (`src/webapp/`) |
| Hosting | Streamlit Community Cloud |
| Tests | pytest (77 tests) |

---

## Project Structure

```
├── app.py                              # Patient-facing Streamlit chat UI — the only file most
│                                        #   changes to "how it looks/feels" touch
├── cli.py                              # Terminal harness for testing agent responses without the UI
├── schema.sql                          # Supabase database schema — source of truth for all tables
├── requirements.txt                    # Python dependencies
├── .env.example                        # Every credential/config value the app needs, undocumented
│                                        #   values left blank — copy to .env for local dev
├── ARCHITECTURE.md                     # Full architecture reference: message flow, all tools per
│                                        #   agent, shared state fields, DB schema
│
├── atlas_dental_clinic_knowledge.md    # Clinic facts (hours, services, staff) — the ONLY source
│                                        #   the FAQ agent is allowed to draw from
├── dental_pricing_faq_knowledge_base.json  # Pricing ranges, insurance types, escalation triggers
│
├── src/
│   ├── agents/
│   │   ├── runner.py                   # Single external entry point — every caller (Streamlit,
│   │   │                                #   CLI) goes through invoke_agent()/stream_agent() here,
│   │   │                                #   never through the manager or a specialist directly
│   │   ├── safety_precheck.py          # Deterministic emergency scan — runs before the manager
│   │   │                                #   sees the message, on every single turn, no exceptions
│   │   ├── manager.py                  # Haiku router — reads state, picks one specialist per turn
│   │   ├── booking_agent.py            # New/existing patient booking, the largest specialist
│   │   ├── triage_agent.py             # Patient-facing follow-up after an emergency alert fires
│   │   ├── exceptions_agent.py         # Identity mismatches, declined consent, anything escalated
│   │   ├── faq_agent.py                # Pricing + clinic knowledge, interrupts and returns
│   │   ├── state.py                    # AtlasDentalState TypedDict — the single object every
│   │   │                                #   node reads from and writes to
│   │   ├── prompts/                    # One markdown system prompt per agent — read these to
│   │   │                                #   understand exactly what each agent is told to do
│   │   └── tools/                      # LangChain @tool definitions, one file per concern —
│   │       ├── consent.py              #   this is where hard rules actually live (e.g. there is
│   │       ├── emergency.py            #   no sign_consent tool, anywhere, on purpose)
│   │       ├── escalation.py
│   │       ├── identity.py
│   │       ├── knowledge.py
│   │       ├── patient_data.py
│   │       └── scheduling.py
│   ├── integrations/                   # Thin wrappers around external services — nothing agent-
│   │   ├── clock.py                    #   specific lives here, just API calls
│   │   ├── clinic_knowledge.py
│   │   ├── pricing_kb.py
│   │   ├── supabase_client.py
│   │   └── gmail_smtp.py
│   │   └── google_calendar.py
│   └── webapp/                         # Staff-facing tools — no conversational agent involved
│       ├── consent_view.py             # Check-in & consent capture (staff, in-person)
│       └── receivables_view.py         # Payment follow-up (staff)
│
└── tests/                              # pytest suite (77 tests) — see `test_non_negotiables.py`
    ├── conftest.py                     #   specifically for how the hard rules are verified
    ├── test_safety_precheck.py
    ├── test_identity.py
    ├── test_patient_data.py
    ├── test_scheduling.py
    ├── test_receivables.py
    ├── test_knowledge.py
    └── test_non_negotiables.py
```

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

## Knowledge Sources

The agent never has clinic facts hardcoded in prompts. All facts come from two files at query time:

- **`atlas_dental_clinic_knowledge.md`** — hours, address, services, CDCP eligibility, staff, procedures
- **`dental_pricing_faq_knowledge_base.json`** — price ranges per procedure, insurance coverage types, escalation triggers

---

## Security Notes

- `.env` and `client_secret.json` are in `.gitignore` — never commit them
- `SUPABASE_SERVICE_ROLE_KEY` is backend-only; it is never passed to the browser
- PHIPA compliance: one individually addressed email per patient — enforced structurally, not by prompt

---

## Local Development

The live demo above covers most needs — clone and run locally only if you're changing code.

<details>
<summary>Setup, running, and tests</summary>

### Setup

```bash
git clone https://github.com/r-baldawa/dental-receptionist-demo.git
cd dental-receptionist-demo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in all values — see the table below
```

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
| `CLINIC_EMERGENCY_ALERT_EMAIL` | Email address(es) that receive emergency alerts (comma-separated for multiple) |
| `CLINIC_FRONT_DESK_BCC_EMAIL` | BCC'd on booking confirmations |
| `APP_ACCESS_PASSPHRASE` | Optional shared passcode gate for the patient-facing chat |

Apply `schema.sql` to your Supabase project (paste into the SQL editor, or `supabase db push`). Tables: `patients`, `appointments`, `consent_records`, `payment_records`, `audit_log`.

### Running

```bash
streamlit run app.py                        # patient-facing chat — http://localhost:8501
streamlit run src/webapp/consent_view.py     # staff: check-in & consent
streamlit run src/webapp/receivables_view.py # staff: payment follow-up
python cli.py                                # terminal harness, no UI
```

### Tests

```bash
pytest
```

77 tests covering safety pre-check, identity resolution, patient data, scheduling idempotency, receivables (PHIPA compliance), knowledge base, and structural non-negotiables.

</details>
