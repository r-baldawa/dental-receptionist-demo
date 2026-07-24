# Atlas Dental Agent — Build Progress

_Updated: 2026-06-28_

---

## Phase 0 — Environment & Scaffolding ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| Repo structure (`src/`, `db/`, `tests/`, etc.) | ✅ Done | All directories and `__init__.py` files in place |
| `requirements.txt` | ✅ Done | langgraph, langchain-anthropic, supabase, etc. |
| `.env.example` | ✅ Done | All required keys documented; real key never committed |
| `.env` created | ✅ Done | All credentials filled in |
| `schema.sql` | ✅ Done | Applied to Supabase; all 5 tables confirmed |
| Supabase smoke test | ✅ Done | All tables reachable via service-role key |
| Gmail SMTP smoke test | ✅ Done | OAuth2 XOAUTH2 working; sends from `atlasdentaltrial@gmail.com` |
| Google Calendar smoke test | ✅ Done | Connected; calendar `atlasdentaltrial@gmail.com`, tz `America/Toronto` |

---

## Phase 1 — Core State, Safety Pre-Check, Manager, Agent Skeletons ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| `src/agents/state.py` — `AtlasDentalState` TypedDict | ✅ Done | `add_messages` reducer; full patient/consent/scheduling state |
| `src/agents/safety_precheck.py` | ✅ Done | Deterministic keyword scan; calls `send_emergency_alert` directly |
| `src/agents/manager.py` | ✅ Done | LLM classification via `with_structured_output(RouteDecision)` |
| All 4 specialist agents (booking, triage, exceptions, faq) | ✅ Done | Real LLM calls; Phase 1 = conversation only |
| `src/agents/runner.py` — `invoke_agent(message, thread_id)` | ✅ Done | Only external entry point; `MemorySaver` checkpointer |
| System prompts (`src/agents/prompts/*.md`) | ✅ Done | All five prompts written |
| `cli.py` and `app.py` wired | ✅ Done | Both import from `src.agents.runner` |
| **Acceptance: emergency keyword fires** | ✅ Verified | Alert email sent; `[gmail_smtp] sent → emergency` in output |
| **Acceptance: manager routes correctly** | ✅ Verified | FAQ, emergency, booking all route correctly |
| **Acceptance: `invoke_agent()` consistent shape** | ✅ Verified | Returns `{text, quick_replies}` across turns |

---

## Phase 1.5 — Tool Layer Audit ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| All tool files created with `@tool` decorators | ✅ Done | 13 tools across 5 files |
| `emergency.py` NOT registered with any agent | ✅ Done | Called only by `safety_precheck.py` directly |
| No `sign_consent` tool exists anywhere | ✅ Done | Only `record_consent_acknowledgement` exists |
| `send_payment_reminder` single-patient enforcement | ✅ Done | Tool signature accepts one `patient_id` only |
| Adversarial audit: each tool structurally can't violate non-negotiables | ✅ Done | Confirmed in tool signatures and booking prompt |

---

## Phase 2 — Booking, Triage, Exceptions Agents (Workflow A) ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| `identity.py` — `lookup_patient_by_contact` | ✅ Done | Exact `.eq()` match (fixed from `.ilike()`); handles conflict case |
| `patient_data.py` — 7 tools | ✅ Done | `create_new_patient` now catches duplicate email (APIError 23505) gracefully |
| `scheduling.py` — 3 tools | ✅ Done | create_appointment, book_calendar_event, send_appointment_confirmation; all idempotency-guarded |
| `escalation.py` — `flag_for_human_review` | ✅ Done | Writes to `audit_log`; flips `registration_status` to `needs_human_review` |
| `consent.py` — `record_consent_acknowledgement` | ✅ Done | No `sign_consent` tool |
| `booking_agent.py` — full tool-calling loop | ✅ Done | 13 tools bound; state extraction from tool results |
| `booking_agent.py` — mid-conversation context note | ✅ Done | `_build_context_note()` injects patient_id/type into system prompt on turns 2+ so agent never re-runs identity lookup |
| `triage_agent.py` — `flag_for_human_review` wired | ✅ Done | Tool-calling loop; audit logging |
| `exceptions_agent.py` — `flag_for_human_review` wired | ✅ Done | Tool-calling loop; sets `requires_human_handoff` |
| `booking_prompt.md` — registration method choice | ✅ Done | After PHIPA consent, agent asks: complete now vs at clinic |
| `booking_prompt.md` — closing message | ✅ Done | Two variants: signatures-only close vs full-registration-at-office close |
| Graph compiles with all tools registered | ✅ Done | Verified via import check |
| Existing patient happy path | ✅ Verified | Tested end-to-end |
| New patient happy path | ⏳ Pending | Duplicate-email crash fixed; needs clean re-test |

---

## Phase 3 — Registration & Consent (Workflow B) ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| Chat-collected data writes to `patients`/`consent_records` | ✅ Done | `create_new_patient` creates patient + 5 pending consent rows |
| Check-In & Consent Capture View (`src/webapp/consent_view.py`) | ✅ Done | Streamlit app; patient search + today's appointments |
| Sign/Decline each consent type in-person | ✅ Done | Writes `signed_at`, `method=in_person_tablet`, `consent_text_version` |
| Signing flips `registration_status` to `active` | ✅ Done | Auto-activates when all required consents are signed |
| `audit_log` entry per consent signature | ✅ Done | Written by `_sign_consent` in webapp |
| **Run webapp:** `streamlit run src/webapp/consent_view.py` | ⏳ Pending | Ready to run; not yet manually tested end-to-end |

---

## Streaming & Latency Improvements ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| Token-level streaming in `app.py` | ✅ Done | `stream_agent()` in runner.py; `st.write_stream()` in app.py |
| `RunnableConfig` passed to all agent LLM calls | ✅ Done | booking, triage, exceptions, faq all accept and forward config |
| Streaming deduplication fix | ✅ Done | Buffers per LLM generation; flushes only on `stop_reason=="end_turn"`; skips `AIMessage` state-update objects |
| Manager switched to Haiku | ✅ Done | `MANAGER_MODEL` env var; defaults to `claude-haiku-4-5-20251001` |

---

## Phase 4 — Receivables Follow-Up (Workflow C) ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| Receivables View (`src/webapp/receivables_view.py`) | ✅ Done | Outstanding/overdue list, multi-select, cooldown warning |
| One-email-per-patient send loop | ✅ Done | `_send_reminder(record)` accepts one patient only — no multi-recipient signature exists |
| 7-day cooldown check | ✅ Done | ASSUMPTION — flag back for clinic policy confirmation |
| `last_followup_sent_at` + `followup_count` updated per send | ✅ Done | Written to `payment_records` after each successful email |
| `audit_log` row per send | ✅ Done | `event_type='payment_reminder_sent'` with balance/email detail |
| **Run:** `streamlit run src/webapp/receivables_view.py` | ⏳ Pending | Not yet manually tested end-to-end (needs test payment_records rows) |

---

## Phase 5 — FAQ Agent ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| `query_pricing_kb` tool | ✅ Done | Keyword match against question_patterns; pre-formatted estimate strings only; hard escalation on guaranteed-price requests |
| `query_clinic_knowledge` tool | ✅ Done | Returns full clinic knowledge doc; agent instructed not to invent details |
| `faq_agent.py` — tool-calling loop | ✅ Done | Replaced `with_structured_output` stub; binds 3 tools; passes config for streaming |
| `faq_prompt.md` — tools section added | ✅ Done | Documents all 3 tools and when to call each |
| `pre_faq_specialist` added to state | ✅ Done | Tracks which specialist was interrupted |
| FAQ interrupt-and-return in `manager.py` | ✅ Done | Saves `pre_faq_specialist` on FAQ entry; clears it on return; LLM instructed to route back |
| FAQ test cases | ⏳ Pending | Needs manual test (TC-D1 through TC-D7) |

---

## Phase 6 — Test Suite & Hardening ✅ COMPLETE

| Task | Status | Notes |
|---|---|---|
| `tests/test_safety_precheck.py` | ✅ Done | TC-A4/A5/A6: keyword detection, mid-flow emergency, no re-fire, turn_count |
| `tests/test_identity.py` | ✅ Done | TC-A1/A3: email/phone match, conflict detection, no-match |
| `tests/test_patient_data.py` | ✅ Done | TC-A2/A7: new patient creation, 5 consent rows, duplicate email, minor detection, balance/no-show |
| `tests/test_scheduling.py` | ✅ Done | TC-A12: create/calendar/confirmation idempotency guards |
| `tests/test_receivables.py` | ✅ Done | TC-C1/C2: one-email-per-patient, no multi-recipient, audit log, cooldown |
| `tests/test_knowledge.py` | ✅ Done | TC-D1–D7: estimate framing, hard escalation, fallback, triage flag, clinic knowledge |
| `tests/test_non_negotiables.py` | ✅ Done | Structural: no sign_consent, no emergency alert in agent tools, precheck in graph |
| **77 tests pass** | ✅ Verified | `pytest tests/ -q` → 77 passed in ~1s |

---

## Open Decisions (from plan.md §7)

- **Appointment duration defaults** — stubbed: 30min checkup/cleaning, 60min procedures (in `google_calendar.py`)
- **Balance policy** — currently notify-only; flag back if clinic wants to block bookings
- **Business hours** — stubbed as Mon–Fri 8am–6pm ET (triage prompt)
- **Provider/calendar mapping** — single default calendar (`GOOGLE_CALENDAR_ID`); multi-provider not built
- **Manager re-evaluation cadence** — re-evaluates every turn (simpler, more LLM calls)
- **No-show deposit threshold** — stubbed at 2+ no-shows; confirm with clinic
