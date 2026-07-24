# Dental Clinic AI Agent — Intake & Scheduling Design (v2)

Updates this version: chat as the primary channel (architected to extend to voice), confirmations sent exclusively via email (Gmail), and appointment invites created through Google Calendar. Builds on `dental_agent_conversational_flow.md`.

---

## 1. Channel Architecture

**Primary channel:** chat (web widget, SMS, or in-app).
**Future channel:** voice — same node logic, different rendering layer.

The key design move: keep conversational *logic* (what to ask, what to capture, how to branch) completely separate from channel *rendering* (how it's displayed/spoken). Node functions return a structured response object; a thin rendering layer formats it per channel.

```python
class AgentResponse(TypedDict):
    text: str                      # core message, channel-neutral
    quick_replies: Optional[list]  # chat-only: e.g. ["Yes", "No"]
    requires_verbal_confirm: bool  # voice-only: trigger explicit read-back
```

**Why this matters for voice-readiness later:**
- Chat can use quick-reply buttons for binary/low-risk questions (emergency check, consent, minor flag). Voice has no buttons — those become explicit yes/no questions with stricter input parsing.
- Chat lets a patient scroll back to re-read something; voice doesn't, so voice needs more frequent verbal read-backs, especially for anything safety-critical (allergies, medications).
- Error-prone fields over voice (email addresses, policy numbers) should fall back to "I'll text/email you a link to enter that yourself" rather than spelling things out character-by-character on a call.
- `channel` is carried in state from the first turn, so any node can check it before deciding how much structure to lean on.

No node logic needs to change to support voice later — only the rendering layer and the input-parsing tolerance.

---

## 2. Confirmation & Scheduling Integrations

- **Confirmations are email-only.** No SMS, no chat-persisted confirmation message as the system of record — the chat session ends, and the confirmation lives in the patient's inbox.
- **Sent via Gmail, using SMTP.** The agent sends through Gmail's SMTP relay (smtp.gmail.com, OAuth2-authenticated) rather than the full Gmail REST API — this is a send-only use case (no inbox reading, labeling, or thread management needed), so SMTP keeps the integration scope minimal.
- **Appointment invites go through Google Calendar.** A calendar event is created with the patient as an attendee (triggering Calendar's native invite email) and assigned to the relevant provider's calendar.

These are two distinct artifacts with two distinct purposes:
| | Calendar invite | Confirmation email |
|---|---|---|
| Contains | Date/time, location, provider, duration | Full appointment summary, allergy/medical flags for staff awareness |
| Trigger | Google Calendar's own invite notification | Agent-composed email via Gmail SMTP |
| Audience | Patient (as calendar attendee) | Patient (primary), optionally CC'd to front desk |

---

## 3. Updated State Schema

```python
class PatientIntakeState(TypedDict):
    channel: Literal["chat", "voice"]
    patient_type: Literal["new", "returning"]
    is_emergency: bool
    consent_given: Optional[bool]
    is_minor: bool
    guardian_info: Optional[dict]
    demographics: dict          # must include a validated email — required for confirmation step
    insurance: dict
    medical_history: dict
    dental_history: dict
    scheduling: dict
    calendar_event_id: Optional[str]
    confirmation_email_sent: bool
    escalation_reason: Optional[str]
    turn_count: int
```

Note: `demographics.email` becomes a hard requirement, not optional — if a patient can't or won't provide an email, the flow can't complete the confirmation step and should route to `human_handoff_node` instead of silently skipping confirmation.

---

## 4. Updated Node Flow

Nodes 1–10 (`greeting_node` through `minor_check_node` / `guardian_consent_node`) are unchanged from the v1 design. Picking up from scheduling:

### `scheduling_node`
> "What days or times generally work for you, and is this for a checkup, cleaning, or something specific?"

**Captures:** preferred days/times, appointment type, urgency
**Added validation:** if `demographics.email` is missing or invalid at this point, branch to `human_handoff_node` before proceeding — there's no point finalizing a booking the agent can't confirm.

### `confirmation_node` (read-back, chat/voice)
> "Here's what I have: [name, appointment type, date/time, allergies/conditions on file]. Does that all look right?"

Unchanged in purpose — still the safety-critical checkpoint before anything is written to calendar or sent by email.

### `calendar_invite_node` *(new)*
**Action:** Create a Google Calendar event:
- Title: `[Patient name] — [Appointment type]`
- Attendees: patient email, provider calendar
- Duration: default by appointment type (e.g. 30 min checkup, 60 min procedure — configurable)
- Description: appointment type + any prep instructions (e.g. "first visit — please arrive 10 min early")

**Captures:** `calendar_event_id`
**Edge logic:** failure to create event (e.g. provider calendar fully booked at requested time) → loop back to `scheduling_node` with an explanation, don't silently pick a different time.

### `send_confirmation_email_node` *(new)*
**Action:** Send via Gmail SMTP:
- Subject: "Your appointment at [Clinic Name] — [date]"
- Body: appointment summary, clinic address/contact, cancellation/reschedule instructions
- Optional BCC to front desk for awareness

**Captures:** `confirmation_email_sent` (boolean)
**Edge logic:** if send fails, retry once, then flag for human follow-up rather than telling the patient "you're confirmed" when the email didn't go out.

### `end_node`
> "You're all set — a confirmation and calendar invite are on their way to [email]. Anything else I can help with?"

---

## 5. Cross-Cutting Notes Carried Forward From v1

- Re-triage on every turn (emergency check isn't a one-time gate)
- Consent before any PHI collection, no exceptions
- Retry/fallback budget per field before escalating to a human
- Separate audit log (consent events, escalations, handoffs) from the conversational transcript

## 6. New Cross-Cutting Notes for v2

- **Email is now a load-bearing field**, not just contact info — validate format at capture time (`demographics_node`), not at send time. Catching a typo early is cheaper than discovering it after the calendar invite has already gone out.
- **Calendar and email actions should be idempotent.** If the flow retries after a transient failure, it shouldn't create a duplicate calendar event or send a duplicate confirmation — check `calendar_event_id` / `confirmation_email_sent` before re-attempting.
- **Voice-channel deferral is explicit, not implicit.** Nothing in nodes 1–15 needs to change to add voice later — only `AgentResponse` rendering and input-parsing tolerance. Worth keeping that boundary clean now so voice isn't a rewrite later.
