# Dental Clinic AI Agent — Conversational Intake Flow

A node-by-node conversational design for a PHIPA-compliant new-patient intake agent, structured to map directly onto a LangGraph state graph. See the companion `dental_agent_intake_flow.mermaid` for the visual flow.

---

## Architecture Note

Each conversational stage below corresponds to a LangGraph node. The graph carries a single shared state object across nodes (a `TypedDict` or Pydantic model), and conditional edges handle the three major branch points: **new vs. returning patient**, **emergency vs. routine**, and **adult vs. minor**.

```python
class PatientIntakeState(TypedDict):
    patient_type: Literal["new", "returning"]
    is_emergency: bool
    consent_given: Optional[bool]
    is_minor: bool
    guardian_info: Optional[dict]
    demographics: dict
    insurance: dict
    medical_history: dict
    dental_history: dict
    scheduling: dict
    escalation_reason: Optional[str]
    turn_count: int  # for fallback/retry logic
```

Conditional edges read off `is_emergency`, `patient_type`, `consent_given`, and `is_minor` to route between nodes. Emergency detection should run as an interrupt-style check on *every* turn early in the conversation, not just once — a patient can disclose "actually my tooth is killing me" mid-flow.

---

## Node-by-Node Design

### 1. `greeting_node`
**Purpose:** Open the interaction, establish patient type.

> "Hi, thanks for calling [Clinic Name] — this is the virtual assistant. Are you an existing patient with us, or is this your first time reaching out?"

**Captures:** `patient_type`
**Edge logic:** `returning` → `verify_identity_node`; `new` → `emergency_triage_node`
**Fallback:** If ambiguous ("I'm not sure / I came in years ago"), ask: "No problem — can I get your name and date of birth so I can check?" and treat as returning-with-verification.

---

### 2. `verify_identity_node` (returning patients)
> "Great, can I get your full name and date of birth to pull up your file?"

**Captures:** name, DOB → match against records
**Edge logic:** match found → `scheduling_node`; no match → `emergency_triage_node` immediately, rather than a separate retry loop. The triage check runs regardless of whether identity confirms, so a patient isn't stuck behind a verification failure if something urgent is going on. If triage comes back routine, the conversation proceeds via the new-patient registration path and the mismatch gets flagged for human review.
**Note:** Never confirm or deny whether a *similar* name exists in the system — that's a privacy leak. Just say "I'm not finding a match — let's get a few details so we can still help you today."

---

### 3. `emergency_triage_node` (new patients, and re-checked on every turn)
> "Before we get into registration — are you experiencing severe pain, swelling, bleeding, or a dental injury right now?"

**Captures:** `is_emergency` (boolean)
**Edge logic:** `true` → `escalation_node` (skip the rest of intake entirely); `false` → `phipa_consent_node`
**Design principle:** This question must come *before* PHIPA consent and before any data collection. Never let a full intake form stand between a patient in pain and help.

---

### 4. `escalation_node`
> "I'm going to get you connected with our team right away so they can advise on next steps — please stay on the line."

**Action:** Transfer to live staff / emergency triage line immediately. Log `escalation_reason`. No further data collection by the agent at this stage — that's for the human to handle.

---

### 5. `phipa_consent_node`
> "Before I collect any health information, I need to let you know: we'll be collecting your personal health information to manage your care and billing, in line with Ontario's PHIPA regulations. This is kept confidential and only shared with parties involved in your treatment, like your insurer. Is it okay to go ahead?"

**Captures:** `consent_given`
**Edge logic:** `true` → `demographics_node`; `false` → `consent_declined_node`
**Compliance note:** This consent must be obtained *before* any of demographics/medical/dental history collection begins — not retroactively. Log timestamp and exact consent language version shown, for audit purposes.

---

### 6. `consent_declined_node`
> "That's completely your choice. Without that information I won't be able to book or manage an appointment electronically, but I can have someone from our front desk call you directly if you'd like."

**Edge logic:** offer → `human_handoff_node` or end conversation gracefully. Do not attempt to collect any further fields.

---

### 7. `demographics_node`
> "Let's start with the basics — can I get your full name, date of birth, and the best phone number and email to reach you?"

**Captures:** name, DOB, gender (optional, offer skip), address, phone, email, emergency contact
**Fallback:** If user provides partial info, ask only for the missing pieces rather than re-asking the whole block.

---

### 8. `insurance_node`
> "Do you have dental insurance you'd like on file? If so, I'll need the provider name, policy number, and group number — and let me know if the plan is under your own name or someone else's."

**Captures:** provider, policy #, group #, subscriber relationship
**Edge logic:** "No insurance" → skip to `medical_history_node`, flag `self-pay` for billing.

---

### 9. `medical_history_node`
> "Now a few health questions so our dentist can treat you safely. Are you currently taking any medications? Any allergies — especially to penicillin, latex, or anesthetics? And do you have any ongoing health conditions like diabetes, heart issues, or a bleeding disorder, or is there any chance you're currently pregnant?"

**Captures:** medications, allergies, conditions, pregnancy flag
**Design note:** Ask pregnancy/sensitive items plainly and without hesitation in tone — phrasing it apologetically can make patients more uncomfortable, not less.

---

### 10. `dental_history_node`
> "What brings you in — is there a specific concern, or is this for a general checkup? And do you have a previous dentist, or know roughly when you last had dental work done?"

**Captures:** chief complaint, previous dentist, last visit date, relevant habits (grinding, smoking) if volunteered or relevant to chief complaint.

---

### 11. `minor_check_node`
**Edge logic:** if DOB from `demographics_node` indicates patient is under 18 → `guardian_consent_node`; else → `scheduling_node`

---

### 12. `guardian_consent_node`
> "Since [patient name] is under 18, I'll need a parent or guardian's name and confirmation that you're authorized to consent to their dental care."

**Captures:** guardian name, relationship, consent confirmation
**Compliance note:** Flag for human review if there's any ambiguity about custody/guardianship authority — the agent should not adjudicate disputed custody situations.

---

### 13. `scheduling_node`
> "Last step — what days or times generally work best for you, and is this for a checkup, cleaning, or something specific?"

**Captures:** preferred days/times, appointment type, urgency level
**Edge logic:** → `confirmation_node`

---

### 14. `confirmation_node`
> "Here's what I have: [read back name, appointment type, date/time, and any flagged allergies/conditions]. Does that all look right?"

**Design principle:** Always read back safety-critical fields (allergies, medical conditions) explicitly, not just scheduling details — this is the last checkpoint before a human dentist sees this data.

**Edge logic:** confirmed → `send_confirmation_node`; correction needed → loop back to relevant node.

---

### 15. `send_confirmation_node`
> "You're all set for [date/time]. I'll send a confirmation to [email] with your appointment details. Anything else I can help with?"

**Action:** Trigger confirmation message/email, close state. No separate form to fill out — everything needed was already captured conversationally.

---

## Cross-Cutting Design Patterns

- **Re-triage on every turn:** A lightweight emergency-keyword check should run before *every* node response, not just at node 3 — patients sometimes disclose pain only after starting the insurance or scheduling conversation.
- **Retry/fallback budget:** Track `turn_count` per node; after 2 failed clarification attempts on any field, route to `human_handoff_node` rather than looping indefinitely.
- **Consent before collection, always:** No demographic, medical, or dental field should be requested before `consent_given == true`, except the emergency check itself (which is a safety screen, not PHI collection in the billing/treatment sense).
- **Audit logging:** Every consent event, escalation, and human handoff should be timestamped and logged separately from the conversational transcript, for PHIPA compliance review.
