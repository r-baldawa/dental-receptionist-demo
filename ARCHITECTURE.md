# Atlas Dental AI — Architecture Reference

A real-time chat agent for Atlas Dental (Toronto). Handles appointment booking, patient registration, emergency triage, receivables follow-up, and FAQ — backed by Supabase, Google Calendar, and Gmail.

---

## How a Message Flows

Every patient message goes through the same path, every single turn:

```
Patient message
      │
      ▼
┌─────────────────┐
│ Safety Pre-check│  ← Deterministic keyword scan. No LLM involved.
│  (safety_       │    If emergency detected → fires alert email immediately,
│   precheck.py)  │    sets active_specialist = "triage", skips manager LLM call.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Manager      │  ← Haiku LLM. Reads conversation + state, picks one specialist.
│  (manager.py)   │    No LLM call if emergency (already routed) or handoff (sticky).
└────────┬────────┘
         │
    ┌────┴──────────────────────────────┐
    │                                   │
    ▼           ▼           ▼           ▼
 booking      triage    exceptions     faq
 agent        agent       agent        agent
    │
    └──► END  (each specialist writes agent_response and returns to END)
```

---

## The Four Specialists

### booking_agent
Handles all appointment booking for new and existing patients.

**Flow:** identity lookup → PHIPA consent → demographics → insurance → medical/dental history → scheduling → calendar + confirmation email

**When routed here:** any appointment booking intent, returning or new patient.

**Appointment types:** `appointment_type` is not free text — the agent picks from a fixed catalogue of 11 real Atlas Dental appointment types defined in `booking_prompt.md` (e.g. `"Dental Cleaning"`, `"Complete Oral Exam and Cleaning (for New Patients)"`), each with its own duration. That exact string drives both the Google Calendar event length (`google_calendar.py::_DURATION_MINUTES`) and the text shown in the confirmation email — the agent is instructed never to invent or reword a type, since anything not in the catalogue silently falls back to a 30-minute default.

**Current-date grounding:** LLMs have no innate sense of "today." `booking_agent` (and `triage_agent`, for business-hours reasoning) inject the real current date/time in `America/Toronto` via `src/integrations/clock.py` into the system prompt on every turn — without this, the agent will infer a plausible-looking but wrong date from training data when a patient says "next Thursday."

---

### triage_agent
Handles the patient-facing response after an emergency is detected.

The emergency alert has **already been sent** by `safety_precheck.py` before this agent runs. This agent focuses on reassuring the patient, assessing severity, and guiding them to an ER if needed.

**When routed here:** whenever `is_emergency = True` in state.

---

### exceptions_agent
Handles cases that can't be resolved automatically.

**When routed here:** identity mismatch (email/phone matches but name/DOB doesn't), PHIPA declined, anything the booking agent flags as needing human review.

---

### faq_agent
Answers pricing and clinic knowledge questions that come up mid-conversation.

**Interrupt-and-return:** if a patient is mid-booking and asks a pricing question, the manager saves `pre_faq_specialist = "booking"`, routes to FAQ. After answering, the next message routes back to booking automatically.

**When routed here:** pricing questions, clinic hours/location/services, CDCP questions.

---

## Tools

### booking_agent Tools (13 tools)

| Tool | What It Does |
|---|---|
| `lookup_patient_by_contact` | Resolves new vs. existing via email/phone DB lookup — never by asking the patient |
| `create_new_patient` | Creates patient row + 5 pending consent records. Status = `pending_consent` |
| `update_patient_insurance` | Writes insurance carrier, policy #, group #, subscriber relationship |
| `update_medical_history` | Records medications, allergies, conditions (tagged "unverified") |
| `update_dental_history` | Records chief complaint, last visit, previous dentist, referral source |
| `update_guardian_info` | Records parent/guardian details for minor patients (under 18) |
| `get_patient_balance` | Checks for outstanding/overdue payment records before booking |
| `get_no_show_history` | Returns no-show count; count ≥ 2 sets `requires_deposit = True` |
| `record_consent_acknowledgement` | Records that PHIPA was explained in chat. **Not a signature.** |
| `create_appointment` | Inserts appointment row. Idempotency: checks for duplicate patient+datetime first |
| `book_calendar_event` | Creates Google Calendar event with `sendUpdates="all"` so the patient actually gets the invite email. Duration looked up from `appointment_type` (see catalogue above). Idempotency: skips if `calendar_event_id` already set |
| `send_appointment_confirmation` | Sends confirmation email. Idempotency: skips if `confirmation_email_sent = True` |
| `flag_for_human_review` | Writes to `audit_log`, flips `registration_status = needs_human_review` |

### triage_agent Tools (1 tool)

| Tool | What It Does |
|---|---|
| `flag_for_human_review` | Logs the emergency case for staff follow-up |

### exceptions_agent Tools (1 tool)

| Tool | What It Does |
|---|---|
| `flag_for_human_review` | Logs the exception and sets status to `needs_human_review` |

### faq_agent Tools (3 tools)

| Tool | What It Does |
|---|---|
| `query_pricing_kb` | Keyword-matches the pricing JSON. Returns pre-formatted estimate strings — never raw numbers. Hard-escalates on "guaranteed price / dispute / treatment plan" |
| `query_clinic_knowledge` | Returns the full clinic knowledge doc for hours, services, location, CDCP, etc. |
| `flag_for_human_review` | Escalates when patient demands a guaranteed price or disputes a bill |

### Not an agent tool (called directly by code)

| Function | Where | Why Not a Tool |
|---|---|---|
| `send_emergency_alert` | `safety_precheck.py` only | Agents must never have discretion over whether to fire an emergency alert |

---

## Knowledge Sources

| Source | Used By | What It Contains |
|---|---|---|
| `atlas_dental_clinic_knowledge.md` | `query_clinic_knowledge` tool | Hours, address, services, CDCP eligibility, parking, accessibility, staff, procedures offered |
| `dental_pricing_faq_knowledge_base.json` | `query_pricing_kb` tool | Price ranges per procedure, insurance coverage type, escalation triggers, fallback response |

The agent never has clinic facts hardcoded in prompts. All facts come from these two files at query time.

---

## Shared State (`AtlasDentalState`)

Every node reads and writes from a single shared state object. Key fields:

| Field | Type | Purpose |
|---|---|---|
| `messages` | `list[BaseMessage]` | Full conversation history (append-only via `add_messages` reducer) |
| `active_specialist` | `str` | Which specialist the manager picked this turn |
| `pre_faq_specialist` | `str` | Saved specialist to return to after FAQ interrupt |
| `is_emergency` | `bool` | Set by `safety_precheck`, never by an agent |
| `patient_id` | `str` | UUID set after identity resolution, used by all subsequent tools |
| `patient_type` | `"new" \| "existing"` | Determines which booking flow to follow |
| `identity_confirmed` | `bool` | True after name+DOB confirmed for existing patients |
| `identity_mismatch` | `bool` | True when email/phone found but name/DOB doesn't match |
| `consent_given` | `bool` | Whether PHIPA was acknowledged in this chat session |
| `requires_human_handoff` | `bool` | Sticks the conversation in `exceptions` once set |
| `calendar_event_id` | `str` | Idempotency guard for calendar booking |
| `confirmation_email_sent` | `bool` | Idempotency guard for confirmation email |
| `last_booking_summary` | `dict` | Set the same turn `confirmation_email_sent` flips to `True`; `runner.py` diffs before/after state to detect a just-completed booking and surfaces this as the structured confirmation card in the UI |
| `agent_response` | `dict` | `{text, quick_replies}` — the turn's output for the UI |

State persists across turns via `MemorySaver` (in-session only). Each session is identified by a `thread_id`.

---

## Receptionist Web Apps

Two Streamlit apps for clinic staff — separate from the patient-facing chat.

### Check-In & Consent Capture
`streamlit run src/webapp/consent_view.py`

- Search patients by name or email
- See today's appointments and each patient's pre-filled chat data
- Sign or decline each consent type in person (tablet)
- Signing all required types flips `registration_status → active`
- Each signature writes to `consent_records` with `method = in_person_tablet`

### Receivables Follow-Up
`streamlit run src/webapp/receivables_view.py`

- Lists all `outstanding` / `overdue` payment records
- Multi-select patients; those within 7-day cooldown are excluded automatically
- Sends one individually addressed email per patient — no batch send signature exists
- Each send increments `followup_count`, sets `last_followup_sent_at`, writes `audit_log`

---

## Non-Negotiables (Enforced in Code, Not Prompts)

These are structural constraints — an agent prompt can drift, a function signature cannot.

| Rule | How It's Enforced |
|---|---|
| Emergency alert fires on every turn, can't be skipped | `safety_precheck_node` runs before manager on every edge from `START` |
| No agent can trigger or skip an emergency alert | `send_emergency_alert` is not in any agent's tool list |
| Consent signing is in-person only | No `sign_consent` tool exists anywhere in the codebase |
| Payment reminders are one-per-patient | `_send_reminder(record: dict)` accepts one record; no batch signature |
| Identity is resolved by DB lookup, not self-report | `lookup_patient_by_contact` is called first; "new or returning?" is UX framing only |
| Pricing is always an estimate, never a guarantee | `query_pricing_kb` returns pre-formatted strings; the tool never exposes raw numbers |

---

## Database Tables (Supabase)

| Table | Purpose |
|---|---|
| `patients` | Core patient record: demographics, insurance, medical flags, registration status |
| `appointments` | Booked appointments with idempotency fields (`calendar_event_id`, `confirmation_email_sent`) |
| `consent_records` | One row per consent type per patient; `status` goes `pending → signed/declined` at check-in |
| `payment_records` | Outstanding/overdue balances with cooldown tracking |
| `audit_log` | Append-only log of escalations, emergency alerts, payment reminders, and consent signatures |

---

## Stack Summary

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph (StateGraph + MemorySaver) |
| LLM — specialists | Claude Sonnet 4.6 |
| LLM — manager routing | Claude Haiku 4.5 (lower latency) |
| Database | Supabase (Postgres) |
| Email | Gmail SMTP via OAuth2 (XOAUTH2) |
| Calendar | Google Calendar API |
| Chat UI | Streamlit (`app.py`) — token-level streaming, live per-step status updates during tool calls, structured booking confirmation card |
| Receptionist UI | Streamlit (`src/webapp/`) |
| Hosting | Streamlit Community Cloud |
| Tests | pytest (77 tests, `pytest tests/`) |
