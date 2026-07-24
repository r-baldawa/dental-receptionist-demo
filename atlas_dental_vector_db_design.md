# Atlas Dental — Clinic Knowledge Vector Store Design (Supabase / pgvector)

How to store atlasdental.ca content for the agent's general-knowledge retrieval, distinct from the structured pricing KB already built.

---

## 1. What's actually on the site (content inventory)

Pulled directly from atlasdental.ca:

- **~150 individual procedure/glossary pages** under "All Dental Services" — e.g. *Root Canal Treatment*, *All-On-4 Dental Implants*, *Dental Crown*, *Wisdom Tooth Removal*, *Scaling and Root Planing*. Each follows a consistent "What Is X? X is..." format. These are already atomic, self-contained answers — a gift for RAG chunking.
- **A handful of long-form guides** — Dental Emergency Guide, Oral Hygiene Guide, Pre-Op/Post-Op Instructions, ODA Fee Guide explainer, Common Orthodontic Problems. These are multi-section articles, structurally different from the glossary pages.
- **Practice info**, scattered across the homepage rather than one page — hours (Mon–Sun, phone consult 7:30 AM–10:00 PM), address (2 Bloor St W #1903, Toronto), phone/fax, "appointment required, not a walk-in clinic," CDCP (Canadian Dental Care Plan) acceptance criteria, free virtual consultation offering.
- **Team/about pages** — Dr. David Nguy, Meet Our Team.
- **Forms & legal pages** — New Patient Form, Consent Forms, Privacy Statement.
- **Bilingual** — English and Chinese (中文) versions of several pages.

This mix is what drives the chunking rules below — it's not one uniform content type.

---

## 2. Where this sits relative to the PHI tables

pgvector gives you similarity search inside the same Postgres database you'd use for the `Patients` / `Appointments` / `Payments` tables from the earlier design — but this should **not** share a schema or RLS policy with those. This is public clinic content, no PHI in it, read-heavy, low-risk. Even within the same Supabase project, keep it in its own schema (e.g. `knowledge`) with its own service-role access, separate from whatever locks down the patient data.

---

## 3. Schema

```sql
create extension if not exists vector;
create schema if not exists knowledge;

create table knowledge.clinic_documents (
    id uuid primary key default gen_random_uuid(),
    source_url text not null,
    title text not null,
    category text not null,        -- 'procedure' | 'guide' | 'practice_info' | 'team' | 'policy'
    service_area text,             -- 'implants' | 'endodontics' | 'cosmetic' | 'orthodontics' | 'general' | 'denture' | 'emergency' | 'holistic'
    language text not null default 'en',
    content text not null,         -- the actual chunk text fed to the LLM
    content_hash text not null,    -- detect re-crawl changes, avoid duplicate embeddings
    embedding vector(1536),        -- match your embedding model's dimension
    metadata jsonb,                -- last_crawled_at, section_heading, page_order, etc.
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (source_url, content_hash)
);

create index clinic_documents_embedding_idx
  on knowledge.clinic_documents using hnsw (embedding vector_cosine_ops);
create index clinic_documents_category_idx on knowledge.clinic_documents (category);
create index clinic_documents_service_area_idx on knowledge.clinic_documents (service_area);
```

---

## 4. Chunking strategy by content type

### Procedure/glossary pages (~150 pages) — one page = one chunk
*Root Canal Treatment*, *All-On-4 Dental Implants*, *Dental Crown*, etc. are already single self-contained answers — don't split them further (split into 2 only if a page genuinely has distinct "what it is" vs. "what to expect" sections that run long).

**Important:** make sure the procedure name is restated inside the chunk text itself, not only in metadata. The chunk is what gets handed to the LLM directly — if it doesn't carry its own context, a retrieved snippet can read as generic ("...is a procedure that involves placing...") without saying which procedure, and the agent can misattribute it.

### Long-form guides — chunk by section
Dental Emergency Guide, Oral Hygiene Guide, Pre-/Post-Op Instructions, Common Orthodontic Problems, ODA Fee Guide explainer. Chunk by H2/H3 heading, ~200–400 tokens each, with the section heading **and** parent page title repeated at the start of the chunk text — not just in metadata — so a chunk about "what to do after a tooth extraction" still makes sense if it's retrieved without its siblings.

### Practice info — one atomic chunk per fact
Hours, address, phone/fax, "appointment required, not a walk-in clinic," CDCP eligibility, virtual consult offering, accepted languages. Don't paragraph-chunk these — a question like "are you open Sundays?" needs a complete, precise answer in one chunk, not half of one (e.g. don't split "Monday: 7:30 AM–10:00 PM" from the rest of the week).

### Team/about — one chunk per provider

### Forms & legal pages — exclude from the RAG store
New Patient Form, Consent Forms, Privacy Statement shouldn't be embedded as retrievable content, for two reasons:
1. Consent language needs to be exact. You already designed `ConsentRecord.consent_text_version` as the canonical source of truth for consent wording — you don't want the agent retrieving-and-paraphrasing a *different* version of that text from a vector chunk.
2. These are forms/actions, not factual Q&A — better surfaced as a direct link than as something the agent answers questions "from."

---

## 5. Two knowledge sources, two retrieval mechanisms — keep them separate

- **Pricing FAQ KB** (`dental_pricing_faq_knowledge_base.json`) stays structured, exact-match lookup by intent — pricing needs a specific range for a specific procedure ID, not approximate semantic retrieval, and it carries its own guardrails (estimate-only framing, hard escalation triggers) that shouldn't get diluted by being treated as just another vector hit.
- **This Supabase vector store** is for general clinic knowledge — "what's a sinus lift," "what do I do after an extraction," "are you open Sundays," "do you take CDCP." Semantic retrieval is the right tool here because patients phrase these many different ways.

Don't merge the two into one index — they have different correctness requirements (exact vs. approximate) and different guardrails.

---

## 6. Ingestion pipeline

1. Crawl each page (procedure pages, guide pages, homepage/about content).
2. Strip nav/footer/boilerplate — the homepage fetch alone has the full nav menu repeated twice; don't embed that.
3. Chunk per the rules above.
4. Compute a `content_hash` (e.g. SHA-256 of the chunk text). On re-crawl, only re-embed chunks whose hash changed — with 150+ procedure pages, this avoids re-embedding everything on every refresh.
5. Generate embeddings, matching the model's output dimension to the `vector(N)` column.
6. Upsert on `(source_url, content_hash)`.
7. Run this on a schedule (weekly is likely enough for fairly static clinic content) rather than per-conversation.

---

## 7. Retrieval at query time

1. Embed the patient's question.
2. `select * from knowledge.clinic_documents order by embedding <=> query_embedding limit 5` (cosine distance) — optionally filtered by `category`/`service_area` if a lightweight intent classification step narrows it first.
3. Set a similarity threshold. If nothing clears it, fall back to "I don't have that specific info, let me have someone from the clinic follow up" rather than answering off a weak match — same fallback pattern as the pricing KB's `fallback_response`.
4. Feed the top-k chunks + question to the LLM for the answer.

---

## 8. Multi-language (English / 中文)

Keep separate rows per language (`language` column) rather than relying on one multilingual embedding space to serve both — filter `where language = detected_language` at query time. More predictable than hoping a single embedding generalizes well across languages at this content volume.

---

## 9. Maintenance note

The site's metadata shows pages do get edited (the clinic's address itself changed with a relocation) — make sure the crawl schedule and `content_hash` check actually catch page-level edits like an address or hours change, not just brand-new pages being added.
