# Atlas Dental AI Agent — Build Plan
**This file is the entry point. Read it first, then read the referenced docs in the order listed before writing any code.**

---

## 1. Project Overview

A chat-first (voice-ready later) AI agent for Atlas Dental that handles:
- **Workflow A** — appointment booking for new and existing patients, including emergency triage
- **Workflow B** — registration and PHIPA consent capture (chat pre-fill + in-person co-sign)
- **Workflow C** — receivables follow-up via a receptionist Web App

This is a real clinic build (Atlas Dental, Toronto), not a generic template — clinic-specific facts live in `docs/atlas_dental_clinic_knowledge.md` and `docs/dental_pricing_faq_knowledge_base.json`. Don't invent clinic details that aren't in those two files.

---

## 2. Source of Truth — Read in This Order

1. **`docs/dental_agent_unified_system_design_v3.md`** — read this first. It supersedes v1/v2 for schema and workflow branching logic. It explicitly references v1/v2 for things it doesn't repeat.
2. **`docs/dental_agent_conversational_flow.md`** and **`docs/dental_agent_intake_design_v2.md`** — full node-by-node dialogue scripts and the channel-abstraction design (`AgentResponse` pattern) that keeps voice support a future rendering-layer change, not a rewrite.
3. **`docs/atlas_dental_clinic_knowledge.md`** and **`docs/dental_pricing_faq_knowledge_base.json`** — the agent's two knowledge sources. Pricing is exact-match lookup; clinic knowledge is loaded into context directly (no retrieval pipeline yet).
4. **`docs/dental_agent_intake_flow.mermaid`** and **`docs/dental_agent_system_architecture.mermaid`** — visual reference for the *workflow logic and branching* (still accurate), not a literal node-by-node implementation map — that's now distributed across the manager and four specialist agents per §3/§4.
5. **`docs/atlas_dental_vector_db_design.md`** — **do not build this in this phase.** It's the plan for *later*, once there's a reason to move off direct context-loading for clinic knowledge.

If anything in this plan.md conflicts with the docs above, the docs win — this file is a build sequence, not a redesign.

---

## 3. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Agent pattern | Manager agent + 4 specialist sub-agents | Not a fine-grained workflow graph. A deterministic safety pre-check runs before any agent sees a message; the manager classifies intent and hands off to one specialist (booking, triage, exceptions, faq) per turn. See §4a. |
| Orchestration | LangGraph (Python) | Used for the manager/handoff layer and each specialist's internal tool-calling loop — not for a many-node fixed sequence. State schema per v3's unified schema. |
| LLM | Anthropic Claude API | Use whatever current model string is appropriate at build time. The manager and each specialist make their own LLM calls; tools themselves never call the LLM. |
| Database | Supabase (Postgres) | One project; relational now, same project can add pgvector later per the deferred design doc |
| Email | Gmail via **SMTP** (OAuth2) | Not the Gmail REST API — send-only use case, per design |
| Calendar | Google Calendar API | Appointment invites only |
| Channel | Chat only, this phase | Agent logic stays channel-agnostic per v2; do not build voice I/O |

### 3a. Agent vs. tool boundary — read this before writing any agent

This is the single most important design decision in the build: **hard constraints live in the tools, not in agent instructions.** An agent can be prompted well and still drift over a long conversation; a tool that structurally can't do the unsafe thing can't drift. Concretely:

- There is **no `sign_consent` tool**. Consent signing is in-person-only via the receptionist Web App (Workflow B) — no agent, including the manager, can finalize a consent record. This isn't a prompt instruction, it's the absence of a function.
- The safety pre-check calls `send_emergency_alert` directly, as plain code — it is not exposed to any agent as an optional tool they choose to invoke. By the time the manager or any specialist sees the message, the alert has already fired if it was going to.
- `send_payment_reminder` (used by the receptionist Web App, not by any conversational agent) only accepts a single `patient_id` per call — there is no multi-recipient signature for an agent or a UI bug to accidentally call.
- `query_pricing_kb` returns pre-formatted estimate-range strings, not raw numbers — the tool's output format enforces "estimate, not guaranteed price," so the FAQ agent can't accidentally state a number as final even under a persistent or cleverly-phrased patient request.

When building a new tool, the test is: *if the agent were adversarially prompted or just confused, could it still misuse this tool to violate a non-negotiable?* If yes, the constraint belongs in the tool's signature/logic, not in a system prompt instruction.

---

## 4. Recommended Repo Structure

```
/docs                      -- design docs (read-only reference, do not edit)
/db
  schema.sql                -- provided, apply to Supabase
/src
  /agents
    state.py                 -- unified state (Patient/Consent/Appointment/Payment/Audit) + conversation/active-specialist state
    runner.py                 -- invoke_agent(message, thread_id) -> dict -- the ONLY external entry point
    safety_precheck.py         -- deterministic, runs first on every turn, before any agent. Calls send_emergency_alert directly when triggered.
    manager.py                  -- intent classification + handoff routing. Fixed routing table; LLM call only for classification.
    booking_agent.py              -- specialist: new + existing booking, scheduling, new-patient data collection (Workflow A + B's chat portion)
    triage_agent.py                -- specialist: post-alert conversational follow-up (the alert itself already fired in safety_precheck)
    exceptions_agent.py             -- specialist: identity mismatch, declined consent, balance/no-show flags
    faq_agent.py                     -- specialist: pricing + clinic knowledge, interrupt-and-return to whichever agent was active
    /prompts
      manager_prompt.md
      booking_prompt.md
      triage_prompt.md
      exceptions_prompt.md
      faq_prompt.md
    /tools
      identity.py                   -- lookup_patient_by_contact (email/phone, Step 0)
      patient_data.py                 -- save_demographics, save_insurance, save_medical_history, save_dental_history, check_minor_status
      scheduling.py                    -- schedule_appointment, create_calendar_event, send_confirmation_email
      emergency.py                      -- send_emergency_alert -- called by safety_precheck directly, NOT offered to any agent as a discretionary tool
      knowledge.py                       -- query_pricing_kb (pre-formatted estimate strings, exact-match), query_clinic_knowledge
      escalation.py                       -- flag_for_human_review
      consent.py                           -- request_consent -- note: no sign_consent tool exists anywhere in this codebase
  /integrations
    gmail_smtp.py
    google_calendar.py
    supabase_client.py
  /webapp                      -- receptionist Web App (Phase 3/4) — check-in/consent view, receivables view. NOT part of the agent system; no conversational agent here.
/tests
  test_cases.md                -- provided
  test_*.py                    -- automated versions of each case, built in Phase 6
.env.example                   -- provided
requirements.txt
README.md
```

---

## 5. Build Phases

### Phase 0 — Environment & Scaffolding
- Create repo structure above.
- Install: `langgraph`, `langchain-anthropic`, `google-api-python-client`, `google-auth-oauthlib`, `supabase`, `python-dotenv`, `pytest`.
- Apply `db/schema.sql` to a Supabase project.
- Populate `.env` from `.env.example`.
- **Acceptance:** Supabase connection confirmed via smoke test; a test email sends successfully via Gmail SMTP; a test event creates successfully via Calendar API.

### Phase 1 — Core State, Safety Pre-Check, Manager, and Agent Skeletons
- Implement the unified state object (Patient/ConsentRecord/Appointment/PaymentRecord/AuditEvent), plus conversation state tracking which specialist is currently "active" for a given `thread_id`.
- Implement `safety_precheck.py` first, before anything else — a deterministic keyword/classifier scan that runs on every incoming message, regardless of which specialist is active. When triggered, it calls `send_emergency_alert` directly as plain code, then hands the (still-unread-by-any-agent) message to `triage_agent` for the conversational follow-up. No agent gets a chance to decide whether the alert fires.
- Implement `manager.py`: a fixed routing table (booking / triage / exceptions / faq) with an LLM call for intent classification when routing isn't obvious from state alone. The manager hands off to one specialist per turn and resumes control when a specialist signals it's done or hits something outside its scope (e.g. FAQ's interrupt-and-return).
- Build all 4 specialist agents as stub tool-calling loops (system prompt + empty toolset for now) — `booking_agent.py`, `triage_agent.py`, `exceptions_agent.py`, `faq_agent.py`.
- Compile with a memory checkpointer (e.g. `MemorySaver`) keyed by `thread_id` so both conversation history and "which specialist is active" persist across calls.
- Add `src/agents/runner.py` exposing `invoke_agent(message: str, thread_id: str) -> dict`, returning `{"text": str, "quick_replies": list | None}`. This is the single integration point external callers (CLI, chat UI, future API) use — they never call the manager or any specialist directly.
- **Acceptance:**
  - Triggering an emergency keyword while a *different* specialist is mid-conversation still fires `send_emergency_alert` — prove the pre-check isn't gated by which agent is active.
  - The manager correctly routes a handful of sample messages to the right specialist (a scheduling request → booking, a pricing question → faq, etc.).
  - `invoke_agent()` is callable from a plain Python script and returns a consistent shape across calls sharing a `thread_id`.

### Phase 1.5 — Tool Layer Audit
Before building out specialist logic in Phase 2+, write the tool stubs listed in §4's `/tools` folder and run the adversarial check from §3a against each one: could a confused or adversarially-prompted agent misuse this tool to violate a non-negotiable? Fix the tool's signature/logic, not the prompt, for anything that fails this check. This is cheap to do now and expensive to retrofit once five agents depend on these tools.

### Phase 2 — Booking, Triage, and Exceptions Agents (Workflow A)
- **`booking_agent`**: implement its tools (`lookup_patient_by_contact` for Step 0, `save_demographics`, `save_insurance`, `save_medical_history`, `save_dental_history`, `check_minor_status`, `schedule_appointment`, `create_calendar_event`, `send_confirmation_email`) and write its system prompt covering both the existing-patient path (confirm identity → reason for visit → provider pref → insurance check → balance flag → recall status → accommodations → no-show check) and the new-patient path (demographics → insurance → medical history → dental history → minor check/guardian consent) from `docs/dental_agent_conversational_flow.md` / `dental_agent_intake_design_v2.md`. `booking_agent` hands off to `exceptions_agent` on identity mismatch and to `triage_agent` if the pre-check fires mid-booking — it doesn't try to handle either itself.
- **`triage_agent`**: implement its (small) toolset — gathering additional symptom detail for the alert, giving ER guidance when severity language is high, business-hours-aware messaging. It has no tool that decides *whether* to alert; that already happened.
- **`exceptions_agent`**: implement `flag_for_human_review` and its system prompt for identity mismatches, declined consent (stop collecting further fields, offer a human callback), balance-blocks-booking vs. notify-only handling, and no-show-history deposit flags.
- **Acceptance:** every test case under "Workflow A" in `test_cases.md` passes — correct specialist handoff sequence, correct DB writes, correct email/calendar side effects (test accounts, not production).

### Phase 3 — Registration & Consent (Workflow B)
- Chat-collected data writes to `patients`/`consent_records` with `registration_status = 'pending_consent'`.
- Build the Check-In & Consent Capture View — minimal viable UI is fine here, doesn't need to be polished this phase.
- **Acceptance:** a chat-completed registration produces a record a receptionist can look up and sign off on; signing flips `registration_status` to `active` and writes `signed_at`/`method`/`consent_text_version` per consent type.

### Phase 4 — Receivables Follow-Up (Workflow C)
- Build the Receivables View (list outstanding/overdue, multi-select).
- Implement the send loop: **one individually addressed email per patient**, never a single multi-recipient send. This is a hard privacy requirement, not a style preference — flag it in code review if you see it implemented any other way.
- **Acceptance:** selecting 3 test patients sends 3 separate emails, each containing only that patient's own balance info; an `audit_log` row per send.

### Phase 5 — FAQ Agent
- Implement `faq_agent`'s tools: `query_pricing_kb` (exact intent match against the JSON, returns pre-formatted estimate-range strings — not raw numbers, per §3a) and `query_clinic_knowledge` (direct context load of the markdown doc).
- Implement the interrupt-and-return handoff in `manager.py` so a side question routes to `faq_agent` and then back to whichever specialist was active, without losing that specialist's progress.
- **Acceptance:** "FAQ" test cases pass, including the pricing KB's hard escalation triggers (guaranteed-price ask, billing dispute, etc.) and the emergency-keyword override — confirm the safety pre-check still fires even when the message looks like a pricing question on the surface ("how much for an emergency exam, I'm in pain").

### Phase 6 — Test Suite & Hardening
- Convert every case in `test_cases.md` into an automated test under `/tests`.
- **Testing caveat specific to this architecture:** tool-call sequences from an LLM-driven agent aren't perfectly deterministic the way fixed node visits were. Assert on invariants instead of exact sequences — e.g. "`send_emergency_alert` was called exactly once," "`send_payment_reminder` was never called with more than one `patient_id`," "the manager handed off to `exceptions_agent` at some point" — rather than asserting the exact order of every tool call. A few sample runs per test case may be needed rather than one deterministic pass.
- Add idempotency checks: a retried booking must not create a duplicate `calendar_event_id`; a retried reminder send must respect `last_followup_sent_at`.
- Confirm audit logging fires on every consent signature, escalation, emergency alert, and payment reminder.
- **Acceptance:** full suite green.

---

## 6. Explicitly Out of Scope for This Build

- Vector DB / embeddings pipeline (`atlas_dental_vector_db_design.md` is future work)
- Voice channel I/O (keep logic channel-agnostic; don't build the voice rendering layer)
- Any clinic content not present in `atlas_dental_clinic_knowledge.md` or the pricing KB — don't fill gaps with plausible-sounding invented detail
- E-sign-ahead-of-visit consent path — in-person signing via the Web App is the only consent method in the current design
- **Giving any agent — including the manager — discretion over a non-negotiable from §3a.** If a future feature request implies an agent should be able to skip the safety pre-check, sign consent, or send a multi-recipient reminder "in some cases," that's a design conflict to flag back, not something to quietly implement via a clever prompt.

---

## 7. Open Decisions — Flag Back, Don't Silently Assume

- Appointment-duration defaults per appointment type
- Whether an outstanding balance blocks booking or is notify-only (clinic policy choice)
- Definition of "business hours" used for the emergency triage branch
- Provider/calendar assignment logic if there's more than one dentist on staff
- Whether the manager re-evaluates routing on every single turn (simpler mental model, more LLM calls) or only at natural decision points — conversation start, a specialist signaling it's done, or the pre-check flagging an interrupt (cheaper, slightly more orchestration code). Recommend the latter, but it's a real tradeoff worth a deliberate call rather than defaulting silently.

If Claude Code hits one of these mid-build, it should stub a sensible default, comment it clearly as an assumption, and surface it rather than guessing silently.
