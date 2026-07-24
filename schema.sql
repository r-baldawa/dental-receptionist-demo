-- Atlas Dental Agent — Operational Schema (Supabase / Postgres)
-- Source of truth: docs/dental_agent_unified_system_design_v3.md, Section 1
-- Apply this in Phase 0. This is the relational schema only — pgvector/knowledge
-- tables are out of scope per docs/atlas_dental_vector_db_design.md (future phase).

create extension if not exists pgcrypto;

-- ============================================================
-- PATIENTS
-- ============================================================
create table patients (
    patient_id          uuid primary key default gen_random_uuid(),
    full_name           text not null,
    dob                 date not null,
    phone               text not null,
    email               text not null,
    address             text,
    emergency_contact   jsonb,
    is_minor            boolean not null default false,
    guardian_info       jsonb,
    insurance           jsonb,
    medical_flags       jsonb,           -- allergies/meds/conditions, tagged unverified until clinical review
    dental_history       jsonb,
    registration_status text not null default 'pending_consent'
        check (registration_status in ('pending_consent', 'active', 'needs_human_review')),
    no_show_count       integer not null default 0,
    recall_status       text,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- Identity resolution keys (Step 0 in the booking workflow). Partial unique
-- indexes so multiple NULLs don't collide with each other.
create unique index patients_email_unique_idx on patients (lower(email)) where email is not null;
create unique index patients_phone_unique_idx on patients (phone) where phone is not null;

-- ============================================================
-- CONSENT RECORDS — one row per consent type, not one blob
-- ============================================================
create table consent_records (
    id                   uuid primary key default gen_random_uuid(),
    patient_id           uuid not null references patients(patient_id) on delete cascade,
    consent_type         text not null
        check (consent_type in ('phipa_privacy', 'treatment', 'assignment_of_benefits', 'financial_policy', 'photo_id')),
    status               text not null default 'pending'
        check (status in ('pending', 'signed', 'declined')),
    signed_at            timestamptz,
    method               text check (method in ('in_person_tablet')),  -- in-person only, per current design
    consent_text_version text not null,
    created_at           timestamptz not null default now(),
    unique (patient_id, consent_type)
);

-- ============================================================
-- APPOINTMENTS
-- ============================================================
create table appointments (
    appointment_id          uuid primary key default gen_random_uuid(),
    patient_id              uuid not null references patients(patient_id) on delete cascade,
    provider_id              text not null,
    appointment_datetime     timestamptz not null,
    appointment_type         text not null,
    status                   text not null default 'scheduled'
        check (status in ('scheduled', 'confirmed', 'completed', 'no_show', 'cancelled')),
    calendar_event_id        text,
    confirmation_email_sent  boolean not null default false,
    requires_deposit         boolean not null default false,   -- set by no-show-history check (TC-A10)
    created_at               timestamptz not null default now()
);

create index appointments_patient_idx on appointments (patient_id);
create unique index appointments_calendar_event_unique_idx on appointments (calendar_event_id) where calendar_event_id is not null;

-- ============================================================
-- PAYMENT RECORDS / RECEIVABLES
-- ============================================================
create table payment_records (
    id                     uuid primary key default gen_random_uuid(),
    patient_id             uuid not null references patients(patient_id) on delete cascade,
    balance_amount         numeric(10,2) not null,
    due_date               date not null,
    invoice_date           date not null,
    payment_link           text not null,
    status                 text not null default 'outstanding'
        check (status in ('outstanding', 'overdue', 'paid')),
    last_followup_sent_at  timestamptz,
    followup_count         integer not null default 0,
    created_at             timestamptz not null default now()
);

create index payment_records_patient_idx on payment_records (patient_id);
create index payment_records_status_idx on payment_records (status);

-- ============================================================
-- AUDIT LOG — separate from clinical record and chat transcript
-- ============================================================
create table audit_log (
    id               uuid primary key default gen_random_uuid(),
    event_type       text not null
        check (event_type in ('consent_signed', 'escalation', 'emergency_alert', 'handoff', 'payment_reminder_sent', 'identity_mismatch')),
    patient_id       uuid references patients(patient_id) on delete set null,
    event_timestamp  timestamptz not null default now(),
    detail           jsonb
);

create index audit_log_patient_idx on audit_log (patient_id);
create index audit_log_event_type_idx on audit_log (event_type);

-- ============================================================
-- ROW LEVEL SECURITY — enable and lock down; backend uses the service
-- role key (which bypasses RLS) for all reads/writes in this design.
-- These tables hold PHI — do not relax this without a deliberate policy.
-- ============================================================
alter table patients enable row level security;
alter table consent_records enable row level security;
alter table appointments enable row level security;
alter table payment_records enable row level security;
alter table audit_log enable row level security;

-- No policies are created here intentionally — default-deny until the
-- backend's service-role access pattern is confirmed in Phase 0.
