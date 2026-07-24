# Dental Clinic AI Agent — Unified System Design (v3)
### Booking · Registration & Consent · Receivables Follow-Up

This combines the conversational flow already designed (`dental_agent_conversational_flow.md`, `dental_agent_intake_design_v2.md`) with the existing-patient detail and agent/human boundary from the reference doc, into three workflows sharing one patient database and one receptionist Web App.

---

## 1. Shared Data Model

One DB underpins all three workflows — the chat agent writes to it during booking/registration, the Web App reads/writes to it at check-in and for receivables.

```python
# Patients
class Patient(TypedDict):
    patient_id: str
    full_name: str
    dob: date
    phone: str                       # unique lookup key — used with email for new-vs-existing identity resolution
    email: str                       # unique lookup key — required, load-bearing for confirmations AND identity resolution
    address: Optional[str]
    emergency_contact: Optional[dict]
    is_minor: bool
    guardian_info: Optional[dict]
    insurance: dict                 # carrier, policy/group #, subscriber relationship, billing pref
    medical_flags: dict             # allergies, meds, conditions — tagged "unverified, pending clinical review"
    dental_history: dict            # chief complaint, last visit, referral source, provider pref
    registration_status: Literal["pending_consent", "active", "needs_human_review"]
    no_show_count: int
    recall_status: Optional[str]    # e.g. "overdue for hygiene", "open treatment plan: crown"

# Consents — one row per consent type, not one blob
class ConsentRecord(TypedDict):
    patient_id: str
    consent_type: Literal["phipa_privacy", "treatment", "assignment_of_benefits", "financial_policy", "photo_id"]
    status: Literal["pending", "signed", "declined"]
    signed_at: Optional[datetime]
    method: Optional[Literal["chat", "in_person_tablet", "e_sign_link"]]
    consent_text_version: str       # which exact wording was shown — for audit

# Appointments
class Appointment(TypedDict):
    appointment_id: str
    patient_id: str
    provider_id: str
    datetime: datetime
    appointment_type: str
    status: Literal["scheduled", "confirmed", "completed", "no_show", "cancelled"]
    calendar_event_id: Optional[str]
    confirmation_email_sent: bool

# Payments / Receivables
class PaymentRecord(TypedDict):
    patient_id: str
    balance_amount: float
    due_date: date
    invoice_date: date
    payment_link: str               # clinic's payment portal / processor link
    status: Literal["outstanding", "overdue", "paid"]
    last_followup_sent_at: Optional[datetime]
    followup_count: int

# Audit Log — separate from clinical record and conversational transcript
class AuditEvent(TypedDict):
    event_type: Literal["consent_signed", "escalation", "emergency_alert", "handoff", "payment_reminder_sent"]
    patient_id: Optional[str]
    timestamp: datetime
    detail: dict
```

---

## 2. Workflow A — Appointment Booking (New & Existing)

### Step 0 — Identity Resolution (new vs. existing)

This is the actual routing decision — not a self-reported "are you new or returning?" answer. The agent resolves identity by querying `Patients` on **email and phone**, which are the lookup keys:

- Email match found → existing patient. Proceed to a lightweight name + DOB **confirmation** (secondary check, not the primary lookup) → existing patient path.
- No email match but phone match found → same as above.
- No match on either → new patient path, even if the patient *says* they've been in before (covers a changed email/phone, or a patient simply misremembering which clinic they visited).
- Email matches one record but phone matches a *different* record → don't guess — flag for human review rather than silently picking one.

The conversational greeting can still ask "new or returning?" for UX flow and to set tone, but it's not what drives branching — the DB match is. This also means email/phone need to be collected (or already known, e.g. from an authenticated chat widget) before this branch point, not after.

### Existing patient path
Lighter-weight than new registration since the record already exists and identity is already resolved in Step 0.

1. **Confirm identity** — quick name + DOB confirmation against the already-matched record; chart ID accepted if offered, but not required. If confirmation fails (name/DOB don't match the record email/phone pointed to), there's no separate retry/transfer subflow — the conversation routes straight into the same emergency-indicators check used for new patients. If that comes back routine, proceed via the new-patient registration path and flag the mismatch for human review, rather than guessing which record is correct.
2. **Reason for visit** — drives urgency/triage and which provider/slot type is needed.
3. **Preferred provider** — continuity of care matters; default to last-seen provider if patient doesn't specify.
4. **Insurance status check** — "Has anything changed since your last visit — new employer or plan?" Only ask, don't re-collect the full insurance block.
5. **Outstanding balance flag** — pull from `PaymentRecord`. Configurable clinic policy: notify-only ("just a heads up, you have an outstanding balance of $X") vs. block booking until resolved. Either way, this is the handoff point into Workflow C if unresolved.
6. **Recall status** — surface if overdue for hygiene or there's an open treatment plan ("you're also due for a cleaning — want to bundle that in?").
7. **Special accommodations** — anxiety/sedation needs, mobility, language preference, captured once and reused on future bookings.
8. **No-show history check** — if `no_show_count` is high, route to a deposit-required or confirmation-call-required flag rather than auto-confirming.
9. → `scheduling_node` → `calendar_invite_node` → `send_confirmation_email_node` (unchanged from v2).

### New patient path
Triggered when Step 0 finds no match on email or phone. Same as the v1/v2 design (demographics → insurance → medical history → dental history → PHIPA consent gate → scheduling), with one structural change: everything the agent collects here is written to `Patient` with `registration_status: "pending_consent"` — nothing is treated as final until a human co-sign happens (see Workflow B).

### Emergency handling (new)
Emergency triage (`emergency_triage_node`) now branches on **staff availability**, not just on the emergency flag:

```
is_emergency == true
  ├─ business hours / live staff available
  │     ├─ attempt warm transfer to live triage line
  │     └─ send emergency_alert_email in parallel (don't wait on transfer success)
  └─ after hours / no live staff
        ├─ send emergency_alert_email immediately
        ├─ if severity signals are high (e.g. "can't stop bleeding", "trauma", "severe swelling"):
        │     tell the patient to go to an ER or emergency dental clinic now
        └─ log AuditEvent for first-thing-next-business-day follow-up
```

**`emergency_alert_email_node`** — fires with *whatever has been captured so far*, even if intake is incomplete. Completeness is not the priority here; speed is.

- **To:** clinic's emergency-intake distribution address / front desk
- **Subject:** `URGENT — Possible dental emergency via [chat/voice] agent`
- **Body:** name (or "not yet captured"), phone/email captured so far, reported symptoms verbatim, channel, timestamp, whether a live transfer was attempted/succeeded

One thing worth confirming with the clinic's privacy officer: whether this kind of emergency-context info sharing needs different consent framing than the standard PHIPA registration consent (PHIPA generally has some allowance for using/disclosing PHI to deal with imminent health risks, but the exact line is worth getting clinic-side legal sign-off on rather than the agent assuming it). Either way, the alert should still fire for safety reasons — that's not something to gate behind a consent flow.

### FAQ / side-intent handling — Pricing & Cost Knowledge Base (Atlas Dental)
Patients ask things mid-flow that aren't part of the linear script. The cost/pricing subset of these is now backed by a real structured knowledge base (`dental_pricing_faq_knowledge_base.json`), modeled on the ODA Suggested Fee Guide (Ontario, CAD) and adapted from Atlas Dental's "Cost of X" FAQ format. It's matched by intent — each entry has its own `question_patterns` array — rather than free-text search, so the agent answers from a specific entry's price range, insurance framing, and any flags rather than generating a number.

**Behavior rules baked into the KB (the agent should follow these, not just the price numbers):**
- Prices are always presented as an estimate or range ("typically costs around / usually ranges from"), never a guaranteed final cost — final pricing depends on the in-person assessment, complexity, and number of surfaces/canals/sites involved.
- The agent never confirms or denies insurance coverage outright — only frames a service as "commonly considered basic / major / cosmetic / supplementary" and points the patient to their insurer or offers a clinic-submitted predetermination.
- If pain, swelling, trauma, or "emergency" comes up alongside a cost question, the KB routes to the `emergency_exam` or `tooth_extraction` / `incision_drainage` entries (both carry `triage_flag: true`) and hands off to `emergency_triage_node` — cost framing never delays that handoff.
- Multi-procedure questions (e.g. "implant + crown + bone graft") get each relevant entry surfaced separately; the agent doesn't guess a combined total.
- Anything not in the KB gets the built-in fallback response — no fabricated numbers, just an offer to book a consultation for a personalized quote.
- Cosmetic procedures (veneers, whitening) always carry an explicit "typically not covered by insurance" note.
- Anything noted "+ Dental Lab Fee" or "+ Dental Materials Expense" gets flagged as not all-inclusive.

**Hard escalation triggers** (from the KB's own `escalate_to_human_if` list) — these bypass the FAQ answer and route to a human rather than letting the agent attempt a response:
- Acute pain, swelling, trauma, or bleeding
- Patient asking for a guaranteed final price rather than an estimate
- Patient disputing a quoted price or a past bill
- A procedure combination needing a custom treatment plan
- Insurance claim disputes or direct-billing eligibility specifics

This is the same "answer inline, then return to wherever the patient was in booking/registration" pattern as before — the KB is now the concrete knowledge source behind it, including its own guardrails, rather than a placeholder.

Non-pricing side-questions (provider availability, cancellation policy, what to bring, appointment length, parking/accessibility, online form availability) follow the same interrupt-and-return pattern but draw from a separate general clinic FAQ source rather than this pricing-specific KB — see `atlas_dental_vector_db_design.md` for how that's stored and retrieved (Supabase/pgvector, semantic search rather than the pricing KB's exact-match lookup).

---

## 3. Workflow B — Registration & Consent Capture

### Path 1: New patient, registered via chat
The agent collects everything in the **"agent can safely collect"** column below conversationally. Nothing in the **"needs human co-sign"** column is finalized by the agent — it's captured as a draft and flagged for in-person sign-off.

| Agent can collect (no signature needed) | Needs human co-sign |
|---|---|
| Name, DOB, contact info, address | PHIPA privacy consent |
| Insurance carrier + member ID (informational, not verified eligibility) | Consent to treatment |
| Chief complaint / urgency / symptoms | Assignment of benefits (insurance signature) |
| Scheduling preferences, provider preference | Photo ID verification |
| Referral source | Final attestation that self-reported medical history is accurate |
| Self-reported allergies/conditions — tagged "unverified, pending clinical review" | |

Result: a **pre-filled registration packet** sitting in the DB with `registration_status: "pending_consent"`.

### Path 2: Patient doesn't register via chat
Existing patients, or new patients who skip the chat pre-registration, complete the full questionnaire in-office (paper or tablet) as today. This data lands in the same `Patient`/`ConsentRecord` tables via front-desk entry — same schema, different entry point, so Workflow B's check-in view doesn't need to know which path the data came from.

### Check-in: Receptionist Web App — Consent Capture View
When the patient arrives:

1. Receptionist looks up the patient (name/DOB or today's appointment list).
2. Web App shows a **read-only summary** of the pre-filled record plus the **specific outstanding consent items** (PHIPA privacy, treatment, assignment of benefits, financial policy, photo ID flag) as signable fields.
3. Patient reviews on-screen (handed to patient, or read aloud by receptionist) and signs — e-signature capture, in person.
4. On submit: each relevant `ConsentRecord` gets `status: "signed"`, `signed_at`, `method: "in_person_tablet"`, and the exact `consent_text_version` shown.
5. Once all required consents are signed, `Patient.registration_status` flips to `"active"`.

This is the same agent/human boundary described in the reference doc, just made concrete as a UI: the agent never signs anything on the patient's behalf — it only gets the packet ready so check-in is a review-and-sign, not a re-keying exercise.

---

## 4. Workflow C — Receivables Follow-Up

### Web App: Receivables View
- List view pulled from `PaymentRecord` where `status` is `outstanding` or `overdue`, with balance, due date, and days-overdue visible — sortable/filterable (e.g. 30/60/90 days) so the receptionist can triage.
- Checkboxes to select one or multiple patients.
- Action button: **"Send Payment Reminder."**

### Send logic — important privacy constraint
Selecting multiple patients must **not** become one email with multiple recipients — that would expose one patient's balance/contact info to another, which is exactly the kind of disclosure PHIPA-style rules are designed to prevent. The Web App should loop through the selection and fire **one individually addressed email per patient via Gmail SMTP**, each personalized with that patient's own balance, due date, and payment link.

**Email template (per patient):**
- **Subject:** "Payment reminder — [Clinic Name]"
- **Body:** name, balance amount, due date, payment link/instructions, contact info if they have questions about the balance

### After sending
- `PaymentRecord.last_followup_sent_at` and `followup_count` updated per patient.
- `AuditEvent` logged (`payment_reminder_sent`) — separate from the clinical record, same audit pattern used for consents and escalations.

---

## 5. Cross-Cutting Notes

- **Identity resolution runs on email/phone, not self-report.** Both Workflow A and Workflow B start with the same lookup against `Patients` — this is one shared piece of logic, not duplicated per workflow.
- **Gmail is the single email integration point**, sent via SMTP (smtp.gmail.com, OAuth2-authenticated) rather than the full Gmail REST API — confirmation emails (A), emergency alerts (A), payment reminders (C) all use the same send-only integration, just three distinct templates/triggers. SMTP is sufficient here since nothing in this system needs to read, label, or thread emails — only send them.
- **Calendar integration uses the Google Calendar API**, scoped to Workflow A only (appointment invites).
- **Pricing FAQ is a separate knowledge source from the patient DB** — the agent reads it but never writes to it, and it carries its own escalation rules independent of the booking/registration logic.
- **Idempotency still matters at the DB level**, not just per-conversation: a retried booking shouldn't create a duplicate `Appointment`/`calendar_event_id`; a retried reminder send should check `last_followup_sent_at` against some cooldown window rather than re-sending on every receptionist click.
- **Audit log is the connective tissue** across all three workflows — it's the one place that shows the full trail (consent signed, emergency alert fired, payment reminder sent) without mixing into the clinical record or the raw conversational transcript.
