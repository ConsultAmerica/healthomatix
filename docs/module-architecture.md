# Healthomatix — Module Architecture

**Date:** 28 Oct 2026  
**Author:** @imtiaz

Healthomatix runs as seven independent modules behind two portals, patient and clinician, over a shared clinical-data core, an AI services layer, and a HIPAA-aligned security and audit foundation. Each module owns its data and exposes a service interface, so any one can ship, scale, or be sold on its own.

> **Implementation note:** Phases **1** and **2** acceptance gates are met in this repo via an in-repo FHIR R4 facade on PostgreSQL (`fhir_resources`, `/api/v1/fhir/R4`) and Document Intelligence ports (Fake OCR/LLM in CI). This is not a claim of HAPI/Medplum parity or HIPAA certification. Live status is tracked in the Cursor canvas `module-architecture.canvas.tsx`.

## At a glance

Requests flow down from the portals to the services, which read and write the record core and call the AI and media services. Approved results and data flow back up. Every layer runs on the security and compliance foundation.

## Module map

| Module | What it owns | Main interface |
|---|---|---|
| Patient Portal | Patient dashboard, upload UI, messages, medication list, reminders | Web and mobile client calling the APIs below |
| Clinician Portal | Doctor dashboard, appointment queue, chart view, consultation workspace | Web client calling the APIs below |
| Document Intelligence | Uploaded files, OCR output, AI-extracted fields, review and verification state | `/documents`, `/extractions`, `/verify` |
| Clinical Records | Verified observations, labs, medications, allergies, conditions, encounters | FHIR R4 REST API |
| Health Trends | Time-series views of results, reference ranges, AI change flags and explanations | `/trends`, `/insights` |
| Consultation | Appointments, secure video sessions, messaging, follow-up plans | `/appointments`, `/sessions`, `/messages` |
| AI Clinical Intelligence | Pre-visit summaries, draft notes, suggested follow-up tasks, all draft until approved | `/summaries`, `/notes`, `/tasks` |

Clinical Records is the single source of truth. Document Intelligence writes to it only after a human verifies an extraction, and AI Clinical Intelligence reads from it but writes nothing a clinician has not approved.

## Non-negotiable rules

1. **Encryption everywhere** — AES-256 at rest, TLS 1.2+ in transit; keys in a dedicated key service for production.
2. **Consent gates every cross-party read** — clinician sees a chart only through active Consent.
3. **Role-based, least-privilege access** — patient, clinician, clinic staff, admin.
4. **AI boundary** — no AI output enters the clinical record without licensed clinician review/approval.
5. **BAA** — every PHI-touching third party (host, OCR, model, video) must be HIPAA-eligible under a signed BAA.
6. **Immutable audit** — every PHI access/change writes an append-only AuditEvent.

## Build phases

| Phase | Gate | Repo status |
|---|---|---|
| 1 · Records core + portals | Sign-in; record stored/viewed under consent; denial audited | **Met** (FHIR facade + consent gate) |
| 2 · Document intelligence | Uploaded lab → verified Observations with provenance | **Met** (Fake OCR/LLM; BAA endpoints for prod) |
| 3 · Health trends | Results plot over time, traceable to source | **Met** (`/trends`, `/insights`; Fake change flags) |
| 4 · Consultation + telehealth | Patient books and completes a video visit | **Met** (`/sessions` Fake video; Encounter + follow-up; messaging existing) |
| 5 · AI clinical support | Clinician approves AI note into chart | **Met** (`/summaries`, `/notes`, `/tasks` + approval gate) |

## Stack (target)

| Layer | Recommended options |
|---|---|
| Portals | Next.js (current) with shared design system |
| Services | Python FastAPI modular monolith (current); split when needed |
| Clinical store | FHIR R4 (facade now; HAPI/Medplum/cloud Healthcare API later) over PostgreSQL |
| Document store | Encrypted object storage |
| OCR | AWS Textract, Google Document AI, or Azure Document Intelligence (BAA) |
| AI | Azure OpenAI or AWS Bedrock under BAA; text endpoints only |
| Telehealth | Vonage, Daily, LiveKit, or Amazon Chime SDK (not Twilio Programmable Video) |
| Identity | OAuth2/OIDC with MFA at IdP; SMART on FHIR later |
| Hosting | HIPAA-eligible cloud under a BAA |

## Related

- [architecture.md](./architecture.md) — ADRs and implementation snapshot
- Phase build prompts live with this brief (Phases 1–5); use Phase 3 next
