# Atlas Dental Agent — Test Case Workflows

Structured as Given/When/Then. Each maps to the build phase that should make it pass (see `plan.md`). Convert these into `/tests/test_*.py` in Phase 6.

---

## Workflow A — Booking

### TC-A1: Existing patient, happy path
- **Given** a patient record exists with matching email and phone
- **When** the patient starts a chat and provides that email
- **Then** the system resolves them as existing via Step 0 lookup (not self-report), confirms name+DOB, skips full registration, asks reason for visit → provider pref → insurance change check → proceeds to scheduling
- **Pass criteria:** no demographics/insurance/medical-history nodes are triggered; `appointments` row created; `calendar_event_id` and `confirmation_email_sent` populate after confirmation

### TC-A2: New patient, happy path
- **Given** no patient record matches the provided email or phone
- **When** the patient books an appointment via chat
- **Then** full new-patient flow runs: demographics → insurance → medical history → dental history → PHIPA consent → scheduling
- **Pass criteria:** `patients` row created with `registration_status = 'pending_consent'`; all consent-requiring fields remain unsigned in `consent_records`

### TC-A3: Identity mismatch (email/phone match, name+DOB doesn't)
- **Given** a patient record matches on email, but the name+DOB given doesn't match that record
- **When** the confirmation step fails
- **Then** the conversation routes immediately into the emergency-indicators check (same node used for new patients) — **not** a retry/human-transfer subflow
- **Pass criteria:** no dedicated "retry identity" node is invoked; if the emergency check comes back negative, the conversation proceeds via the new-patient path and an `audit_log` entry flags the mismatch for human review

### TC-A4: Emergency disclosed at start, during business hours
- **Given** current time is within configured business hours
- **When** the patient indicates severe pain/swelling/trauma at the emergency triage check
- **Then** the system attempts a warm transfer to live staff AND sends `emergency_alert_email` in parallel — it does not wait for transfer success before sending the alert
- **Pass criteria:** alert email contains whatever name/contact info was captured so far, even if incomplete; `audit_log` entry created

### TC-A5: Emergency disclosed after hours
- **Given** current time is outside configured business hours
- **When** the patient indicates an emergency
- **Then** the system sends the alert email immediately (no transfer attempt), and if severity language is high (e.g. "won't stop bleeding," "trauma") tells the patient to go to an ER/emergency clinic now
- **Pass criteria:** alert fires with partial data if intake is incomplete; `audit_log` entry flagged for next-business-day follow-up

### TC-A6: Emergency disclosed mid-flow (not at the triage checkpoint)
- **Given** a patient is partway through scheduling and says "actually my tooth is killing me"
- **Then** the re-triage check (which runs on every turn, not just once) catches this and routes to emergency handling immediately
- **Pass criteria:** the agent does not finish collecting scheduling preferences before responding to the emergency signal

### TC-A7: Minor patient
- **Given** DOB indicates the patient is under 18
- **When** the new-patient flow reaches the minor check
- **Then** guardian identity + consent capture is triggered before scheduling
- **Pass criteria:** `guardian_info` populated; scheduling does not proceed without it

### TC-A8: PHIPA consent declined
- **Given** a new patient is asked for PHIPA consent
- **When** they decline
- **Then** the agent stops collecting any further fields and offers a callback/human handoff
- **Pass criteria:** no demographics/medical/dental fields are written after the decline; no `patients` row is partially populated beyond what was already given pre-decline

### TC-A9: Outstanding balance during existing-patient booking
- **Given** an existing patient has a `payment_records` row with `status = 'overdue'`
- **When** they try to book
- **Then** the balance is surfaced per clinic policy (notify-only or block, per the open decision in plan.md §7) — test both configurations
- **Pass criteria:** notify-only config lets booking proceed after the notice; block config halts booking until resolved

### TC-A10: High no-show history
- **Given** `no_show_count` is above the configured threshold
- **When** booking proceeds
- **Then** a deposit-required or confirmation-call-required flag is set on the appointment
- **Pass criteria:** flag present on the `appointments` row

### TC-A11: Missing/invalid email blocks confirmation
- **Given** a patient won't provide a valid email
- **When** the flow reaches scheduling
- **Then** it routes to human handoff before finalizing, rather than booking without a way to confirm
- **Pass criteria:** no `appointments` row is finalized; handoff reason logged

### TC-A12: Idempotent retry after transient Calendar failure
- **Given** `calendar_invite_node` fails once (simulated API error) then succeeds on retry
- **When** the retry runs
- **Then** only one `calendar_event_id` is created and only one confirmation email is sent
- **Pass criteria:** no duplicates; `confirmation_email_sent` is checked before re-sending

---

## Workflow B — Registration & Consent

### TC-B1: Chat pre-fill → in-person sign-off
- **Given** a new patient completed chat registration (`registration_status = 'pending_consent'`)
- **When** the receptionist opens the Check-In & Consent Capture View for that patient
- **Then** the view shows a read-only summary plus the specific outstanding consent items as signable fields
- **Pass criteria:** signing all required items flips `registration_status` to `'active'`; each `consent_records` row gets `status='signed'`, `signed_at`, `method='in_person_tablet'`, and `consent_text_version`

### TC-B2: Partial consent at check-in
- **Given** a patient signs PHIPA privacy and treatment consent but declines assignment of benefits
- **Then** `registration_status` remains `'pending_consent'` (not all required items signed) and the declined item is recorded as `status='declined'`, not left blank

---

## Workflow C — Receivables

### TC-C1: Bulk reminder send is individualized, not multi-recipient
- **Given** 3 patients are selected in the Receivables View, each with different balances
- **When** "Send Payment Reminder" is triggered
- **Then** 3 separate emails are sent via Gmail SMTP, each addressed to one patient with only that patient's balance/due date/payment link
- **Pass criteria:** **no email contains more than one patient's financial information** — this is the single most important assertion in this test file. Also check `last_followup_sent_at` and `followup_count` increment per patient, and 3 separate `audit_log` rows are created

### TC-C2: Reminder cooldown / idempotency
- **Given** a patient's `last_followup_sent_at` is within the configured cooldown window
- **When** a receptionist selects them again and sends
- **Then** either the send is blocked with a warning, or it proceeds but doesn't double-count — confirm whichever behavior is implemented matches the intended policy (flag if undecided)

---

## FAQ / Knowledge Integration

### TC-D1: Pricing question mid-booking, interrupt-and-return
- **Given** a patient is mid-scheduling
- **When** they ask "how much is a root canal?"
- **Then** the agent answers from `dental_pricing_faq_knowledge_base.json` as a range/estimate, then returns to exactly where scheduling left off
- **Pass criteria:** answer includes the estimate framing language; no scheduling state is lost or reset

### TC-D2: Pricing question with emergency keywords
- **Given** a patient asks "how much for an emergency exam, I'm in a lot of pain"
- **Then** the system routes to emergency triage instead of just answering the price question
- **Pass criteria:** triage check fires before or alongside the pricing answer; cost framing does not delay it

### TC-D3: Multi-procedure cost question
- **Given** a patient asks "how much for an implant plus a crown and bone graft"
- **Then** each relevant KB entry (`dental_implant`, `dental_crown`, `bone_graft`) is surfaced separately
- **Pass criteria:** the agent does not output a single combined total

### TC-D4: Guaranteed-price request → hard escalation
- **Given** a patient asks "just tell me the exact final price, not an estimate"
- **Then** this hits the KB's `escalate_to_human_if` trigger and routes to a human rather than the agent attempting a number
- **Pass criteria:** no specific guaranteed dollar figure is given by the agent

### TC-D5: Procedure not in the pricing KB
- **Given** a patient asks about a procedure with no KB entry
- **Then** the fallback response fires — no fabricated number, offer of a personalized quote/consultation
- **Pass criteria:** response matches the KB's `fallback_response` pattern

### TC-D6: General clinic knowledge question
- **Given** a patient asks "are you open on Sundays?" or "do you take the CDCP?"
- **Then** the agent answers directly and confidently from `atlas_dental_clinic_knowledge.md` (Section 1/2 — high-confidence practice info)
- **Pass criteria:** correct hours/CDCP eligibility info returned, no hedging language needed for this category

### TC-D7: Clinical detail beyond what the knowledge doc covers
- **Given** a patient asks a detailed clinical question about a long-tail procedure that only has a name (no description) in `atlas_dental_clinic_knowledge.md` Section 4
- **Then** the agent confirms the clinic offers it but defers detailed clinical explanation to a consultation rather than inventing detail
- **Pass criteria:** no fabricated clinical claims beyond what's in the document
