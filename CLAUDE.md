# CLAUDE.md

## Project
Atlas Dental AI agent — chat-first (LangGraph + Claude API), handling appointment booking, registration/consent capture, and receivables follow-up for a real Toronto dental clinic. Not a generic template; clinic facts are real and come from specific files, not memory.

## Read before building anything
- **`plan.md`** — build sequence, phases, acceptance criteria. Follow phase order; don't jump ahead.
- **`docs/dental_agent_unified_system_design_v3.md`** — source of truth for data model and workflow branching. Wins over anything else if there's a conflict.
- **`docs/dental_agent_conversational_flow.md`** + **`docs/dental_agent_intake_design_v2.md`** — node-by-node dialogue scripts and the channel-abstraction pattern (keeps voice a future rendering change, not a rewrite).
- **`docs/atlas_dental_clinic_knowledge.md`** + **`docs/dental_pricing_faq_knowledge_base.json`** — the only sources of clinic facts and pricing. Don't invent clinic details that aren't in these two files.
- **`test_cases.md`** — Given/When/Then workflows; convert to `/tests` in Phase 6.
- **`schema.sql`** — apply as-is to Supabase in Phase 0. If it needs to change, update `dental_agent_unified_system_design_v3.md` first, then the schema — not the other way around.
- **`.env.example`** — required credentials. Never commit a real `.env`.

## Stack
LangGraph (Python) + Claude API + Supabase (Postgres) + Gmail via SMTP + Google Calendar API. Chat channel only this phase.

## Architecture — read plan.md §3/§3a/§4 for full detail
A deterministic safety pre-check runs before any agent sees a message. A manager agent then routes to one of four specialists per turn: `booking_agent`, `triage_agent`, `exceptions_agent`, `faq_agent`. The core rule: **non-negotiables live in tool signatures, not in agent prompts** — an agent can drift under a long or adversarial conversation, a tool that structurally can't do the unsafe thing can't.

## Non-negotiables
These are deliberate design decisions, not arbitrary — don't "simplify" past them. Each is enforced at the tool/code level, listed below, not just stated in a prompt:
- **Receivables emails:** one individually addressed email per patient, never one email to multiple patients. Enforced by `send_payment_reminder` only accepting a single `patient_id` per call — there is no multi-recipient signature to misuse.
- **Consent signing:** in-person only, via the receptionist Web App. There is no `sign_consent` tool anywhere in this codebase — not for the manager, not for any specialist. Chat-collected data is a draft, never a final signature.
- **Identity resolution:** new vs. existing is decided by `lookup_patient_by_contact` (email/phone lookup), called by `booking_agent` — not by asking "are you new or returning?" That question is UX framing only, never the routing logic.
- **Identity mismatch:** hands off to `exceptions_agent`. No separate retry/transfer tool exists for this case.
- **Emergency triage:** lives entirely in `safety_precheck.py`, which runs before the manager or any specialist sees a message, on every single turn — not something any agent can skip, defer, or decide isn't necessary this time. `send_emergency_alert` is called directly from there, not offered to agents as a discretionary tool.

## Out of scope this phase
- Vector DB / embeddings — `docs/atlas_dental_vector_db_design.md` is future work, not this build.
- Voice I/O — keep agent logic channel-agnostic; don't build the voice rendering layer.
- Any clinic detail not present in the clinic knowledge doc or pricing KB.
- Giving any agent — including the manager — discretion over a non-negotiable above. If a request implies an agent should bypass one "in some cases," that's a design conflict to flag back, not something to solve with a cleverer prompt.

## Commands
To be filled in once Phase 0 scaffolding exists. Expected:
- Test: `pytest`
- Install: `pip install -r requirements.txt`

## Open decisions — don't silently assume
See `plan.md` §7: appointment-duration defaults, balance-blocks-booking vs. notify-only policy, business-hours definition for triage, multi-provider calendar mapping. If you hit one of these, stub a sensible default, comment it clearly as an assumption, and surface it — don't guess silently and move on.
