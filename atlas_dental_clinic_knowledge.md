# Atlas Dental — Clinic Knowledge Document (Agent-Ready Reference)

Compiled from atlasdental.ca. Built to be loaded directly into an agent's context (system prompt / knowledge attachment) — no vector DB or retrieval pipeline required for now. Pair with `dental_pricing_faq_knowledge_base.json` for pricing/insurance framing; this document does not duplicate that content.

---

## 1. Practice Information

| Field | Detail |
|---|---|
| Name | Atlas Dental |
| Location | 2 Bloor St W, Suite 1903, Toronto, ON M4W 3E2 (Yonge & Bloor — subway access at Bloor-Yonge Station) |
| Note | Relocated to this address in January 2025; previously at a different downtown Toronto location |
| Phone | 416-597-0534 |
| Fax | 437-317-3386 |
| Lead dentist | Dr. David Nguy |
| Languages | English, Chinese (中文) — separate Chinese-language pages and new patient form available |
| Reputation | 700+ Google reviews, 5-star average |
| Positioning | Downtown Toronto dentist for general, emergency, implant, and orthodontic dentistry |

---

## 2. Policies & Booking

- **Appointment required** — Atlas Dental is **not a walk-in clinic**. Even emergencies need to be booked (by phone or online).
- **Phone consult hours:** Monday–Sunday, 7:30 AM – 10:00 PM (available 7 days a week for the free phone consult line, not necessarily in-clinic treatment hours).
- **Free virtual consultation** offered by phone — for second opinions, orthodontic questions, or emergencies — before committing to an in-person visit.
- **Online booking** available directly for new patient exams and other appointment types.
- **CDCP (Canadian Dental Care Plan):** accepted. Eligibility per the federal program: Canadian residents with adjusted family net income under $90,000 and no access to other dental insurance.
- **Contact form fields** collected on the site: first name, last name, email, mobile phone, message, optional photo/X-ray upload (PDF/PNG/JPG, max 1MB each) — useful reference if replicating their intake form fields.

---

## 3. Service Categories (top-level site structure)

Atlas Dental organizes its offering into eight categories — useful as the top-level taxonomy for intent classification:

1. Emergency Dental Services
2. Orthodontic Services
3. Dental Implant Services
4. Holistic Dentistry
5. Endodontic Services
6. Cosmetic Dentistry
7. General Dentistry
8. Denture Services

---

## 4. Procedure Directory (by category)

Names only — confirms *what's offered* for "do you do X?" style questions. For anything beyond a yes/what-it-is answer, direct the patient to a consultation; don't improvise clinical detail from a name alone.

**Diagnostics & Imaging:** Complete Oral Exam, New Patient Dental Exam, Digital Dental X-Rays, Bitewing X-Rays, Periapical X-Rays, Panoramic X-Ray, CBCT Scan, Intraoral 3D Scanner

**Restorative (fillings, crowns, bridges, inlays/onlays):** Tooth Filling, Composite Resin Filling, Amalgam Filling, Glass Ionomer Filling, Dental Amalgam Filling Replacement, Mercury Filling Removal, SMART Amalgam Removal, Dental Crown, Gold Dental Crown, Zirconia Dental Crown, Lithium Disilicate Dental Crown, Porcelain Fused To Metal Dental Crown, Dental Crown Recementation, Dental Bridge, Cantilever Dental Bridge, Gold Dental Bridge, Zirconia Dental Bridge, Lithium Disilicate Dental Bridge, Maryland Dental Bridge, Porcelain Fused To Metal Dental Bridge, Dental Bridge Recementation, Porcelain Inlay, Porcelain Inlay Recementation, Porcelain Onlay, Porcelain Onlay Recementation

**Cosmetic:** Dental Veneers, Composite Veneers, Feldspathic Porcelain Veneers, Lithium Disilicate Veneers, Zirconia Veneers, Dental Veneers Recementation, Icon Resin Infiltration, Smile Makeover, In-Office Teeth Whitening, Take-Home Teeth Whitening Trays

**Endodontic (root canal-related):** Root Canal Treatment, Root Canal Retreatment, Pulpotomy, Pulpectomy, Dental Pulp Capping, Direct Pulp Capping, Indirect Pulp Capping, Apicoectomy, Bioceramic Root Canal Sealers

**Oral Surgery & Extractions:** Tooth Removal/Extraction, Wisdom Tooth Removal, Coronectomy, Dry Socket Treatment, Abscess Drainage (Incision & Drainage)

**Periodontal:** Scaling and Root Planing, Gum Graft

**Implants — techniques & types:** Dental Implants (general), Titanium Dental Implants, Zirconia Dental Implants, Ceramic Dental Implants, Endosteal Dental Implant, All-On-4, All-On-6, All-On-X, 3 On 6, Teeth In A Day, Immediate Dental Implant Placement, Computer Guided Dental Implant Surgery, Dental Implant Removal, Dental Implant Crown, Dental Implant Bridge, Implant Denture, Tooth Supported Overdenture

**Bone & sinus procedures (implant-adjacent):** Dental Bone Graft, Alveolar Bone Preservation, Lateral Window Sinus Lift, Indirect (Crestal) Sinus Lift

**Dentures:** Complete Denture, Immediate Complete Denture, Partial Denture, Acrylic Partial Denture, Cast Partial Denture, Valplast Flexible Partial Denture, Single Tooth Denture, Essix Denture, Denture Repair, Denture Reline

**Orthodontics:** Invisalign Clear Aligners, Fixed Orthodontic Retainers, Removable Orthodontic Retainers, Hawley Retainer

**Night guards, sedation & pain management:** Night Guard (general), Hard Acrylic Night Guard, Soft Night Guard, Dual Laminate Night Guard, NTI Night Guard, Sports Mouth Guard, Nitrous Oxide Sedation, Oral Conscious Sedation, Dental Pain Medication, Antibiotic Prescription For Dental Infection, Silver Diamine Fluoride

---

## 5. Detailed Reference — Commonly-Discussed Procedures

Brief, plain-language descriptions for the procedures patients ask about most (these overlap with `dental_pricing_faq_knowledge_base.json` for pricing — check that file for cost/insurance framing rather than duplicating it here):

- **Root Canal Treatment** — removes infected/damaged pulp from inside a tooth to save it rather than extract it; also called endodontic therapy.
- **Tooth Extraction** — removal of a tooth from its socket, typically when it's too damaged or problematic to restore.
- **Wisdom Tooth Removal** — extraction specifically addressing third molars, often due to impaction or crowding.
- **Abscess Drainage (Incision & Drainage)** — relieves pain and clears infection from a swollen, infected area.
- **Dry Socket Treatment** — addresses a painful condition that can occur after an extraction when the healing blood clot is disrupted.
- **Dental Crown** — a custom cap placed over a damaged or decayed tooth to restore shape and function.
- **Dental Bridge** — a fixed prosthetic that spans the gap left by one or more missing teeth.
- **Dental Veneers** — thin custom shells bonded to the front of teeth for cosmetic improvement.
- **Teeth Whitening** — available both in-office and as take-home tray kits.
- **Invisalign** — clear aligner therapy as an alternative to traditional braces.
- **Dental Implants** — a tooth-root replacement (commonly titanium or zirconia) topped with a crown, bridge, or denture; All-On-4/6/X and Teeth-in-a-Day are full-arch variations for patients missing most or all teeth in an arch.
- **Scaling and Root Planing** — a deep-cleaning procedure (non-surgical) for gum disease, beyond a standard cleaning.
- **Night Guards** — custom oral appliances worn during sleep to protect against grinding/clenching; available in hard, soft, and dual-laminate materials.

---

## 6. Emergency-Relevant Procedures (as curated on the site itself)

Atlas Dental's own "Emergency Dental Services" section groups these as the relevant procedures for urgent situations — useful for mapping a patient's described symptom to a likely-relevant procedure during triage:

Tooth Extraction, Wisdom Tooth Extraction, Root Canal Treatment, Abscess Drainage, Dry Socket Treatment, Dental Pain Medication, Antibiotic Prescription for Dental Infection, Pulpotomy, Pulpectomy, Dental Pulp Capping, and recementation procedures for crowns/bridges/veneers/inlays/onlays that have come loose.

**Agent note:** this list is for *recognizing* what kind of issue a patient might be describing — it is not a substitute for the emergency triage flow already built (`emergency_triage_node`). A patient describing pain, swelling, trauma, or a "knocked out tooth" still goes through triage first; this section just helps the agent understand what's likely going on, not skip the safety check.

---

## 7. Implant Brands/Systems Referenced on the Site

Atlas Dental's site has individual pages for these implant manufacturers/systems: Nobel Biocare, Straumann, Osstem, MegaGen, Astra Tech, Camlog, BioHorizons, Hiossen, MIS, Neodent, Neoss, Adin, Alpha-Bio Tec, Ankylos, Bicon, Blue Sky Bio, DTI, Euroteknika (ETK), IDL, Implant Direct, Titan, Zimmer Biomet, ACE Surgical.

**Agent note:** these pages read as general educational/glossary content about each manufacturer, not necessarily a confirmed statement that Atlas Dental exclusively uses or stocks every one of these brands for every case. If a patient asks specifically "do you use [brand] implants," it's safer to confirm with the clinic/treating dentist rather than affirm from this list alone — brand choice is typically a clinical decision made per case.

---

## 8. Financial & Community Programs

- **CDCP (Canadian Dental Care Plan)** — accepted; see eligibility note in Section 2.
- **Financing & Payment Plans** — referenced in site navigation as a dedicated resource; specific terms weren't pulled into this document — confirm current terms directly with the clinic before quoting anything specific to a patient.
- **MyStudentPlan** and **Studentcare** — student dental benefit programs the clinic appears to work with, aimed at Ontario post-secondary students.
- **Free Dental Services for Refugees** — emergency dental care referenced under Canada's Interim Federal Health Program (IFHP).
- **Terracycle recycling program** — the clinic accepts oral care waste (e.g. toothbrushes, floss containers) for recycling.

---

## 9. Deliberately Excluded From This Document

- **Pricing/insurance-coverage framing** — lives in `dental_pricing_faq_knowledge_base.json`, not duplicated here.
- **Consent Forms, New Patient Form, Privacy Statement** — legal/form content. Don't have the agent answer questions "from" these; the actual consent language used in your own flow should come from your `ConsentRecord.consent_text_version`, not a paraphrase of the website's version.
- **Blog content** — marketing/news, not stable factual reference.
- **Reviews** — social proof, not something the agent should quote or fabricate from.

---

## 10. How the Agent Should Use This Document

- Treat Sections 1–3 (practice info, policies, categories) as **high-confidence, exact-answer** material — these are facts, not approximations.
- Treat Sections 4–7 (procedure directory, descriptions, emergency mapping, implant brands) as **awareness-level** reference — confirms what's offered and gives a one-line plain-language gist, but isn't a substitute for the dentist's actual clinical explanation. If a patient wants more than a one-line description, the honest move is "that's worth discussing with the dentist directly" rather than extrapolating further detail that isn't in this document.
- If a question falls outside this document entirely, use the same fallback pattern as the pricing KB: say so plainly and offer a consultation, rather than guessing.
- This document should be refreshed periodically (the site does get edited — the clinic's address changed at the start of 2025) — worth a re-pull every so often rather than treating this as permanently static.
