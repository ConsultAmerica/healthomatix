# Healthomatix phased backlog

Dependencies are explicit; a later item must not be presented as operational
until its security and workflow gates pass.

## Phase 0 — completed audit/proposal

- [x] Read-only MediGuide audit and selective reuse matrix.
- [x] Separate Healthomatix architecture decision and safety boundary.
- [x] Proposed module inventory, ER design, API surface, navigation, and
  phased backlog.

## Phase 1 — foundation

| ID | Work item | Depends on | Acceptance evidence |
|---|---|---|---|
| P1-01 | Workspace/package structure for Expo app, Next.js portals, FastAPI API, shared API contracts, migrations, and docs. | None | **Implemented.** Separate workspaces; no MediGuide files changed. |
| P1-02 | OIDC configuration/validation adapter and server-side current-user resolution. | P1-01 | **Implemented.** HTTPS issuer/audience/key validation tests; missing config fails closed; no first-party password table. |
| P1-03 | Organization/clinic, location, membership, internal user identity, user-keyed patient profile, tenant-scoped clinic-patient link, provider profile, and credential-state models. | P1-02 | **Implemented.** Alembic chain and SQLite test schema; tenant-integrity and state constraints. This is not yet a separate `PatientIdentity` model or a fully clinic-scoped chart/profile model. |
| P1-04 | Tenant-scoped authorization dependencies and resource query helpers. | P1-03 | **Implemented.** Cross-tenant, cross-user, wrong-role, and inactive-member tests. |
| P1-05 | Versioned consent grants/withdrawals and atomic audit event writes. | P1-03, P1-04 | **Implemented.** Grant/withdrawal and transactional audit tests; no payload/PHI in audit serializer. |
| P1-06 | Private document metadata and `PrivateDocumentStorage` port. | P1-04, P1-05 | **Partial.** Unconfigured backend fails closed and metadata owner/tenant isolation is tested; private storage provider, synthetic-only test adapter, and binary-transfer consent checks remain unavailable. |
| P1-07 | Next.js clinic and patient portals with role-aware navigation and accessible loading/error/unavailable states. | P1-02, P1-04 | **Implemented, not production-verified.** Route-based clinic and patient portals call the live API through an encrypted server-side session (OIDC + PKCE) and same-origin proxy with CSRF checks. Not yet verified against a real identity provider. Cross-tenant authorization is covered by backend tests. |
| P1-08 | Expo patient shell with the five primary navigation destinations. | P1-02, P1-04 | **Implemented.** Expo Router shell and SecureStore adapter boundary; sign-in and live-data use remain disabled. |
| P1-09 | OpenAPI-backed API contract documentation and generated client boundary. | P1-02 through P1-06 | **Implemented.** Generated OpenAPI/type client with stale-output check and tests that future document routes are not mounted. |
| P1-10 | Restricted SaaS administration foundation for tenant provisioning and support access policy; no clinical-record browsing. | P1-03, P1-04 | **Foundation implemented.** Exact configured identity allowlist, tenant metadata/provisioning, and audited pending support requests; no support grant or clinical-record access. |
| P1-11 | Security/privacy review, tests, and local developer setup. | P1-01 through P1-10 | **Partial.** Focused tests and local setup are documented; remaining P1-06/P1-07 gates prevent Phase 1 sign-off. |

The current npm dependency audit reports 19 high-severity findings in the
Expo/Metro/React Native dependency tree and no critical findings after the
Next.js security update. The suggested aggregate npm remediation downgrades
the mobile framework to unsupported older majors, so it was not applied.
Keep this preview out of production and re-evaluate when a compatible patched
Expo SDK/dependency set is available.

### Architecture constraints carried forward

- A global patient identity can have multiple tenant-specific clinic-patient
  relationships; no clinic membership implies cross-clinic record access.
- Healthomatix is initially a clinic workflow layer that complements existing
  EHRs; the backlog does not imply a validated replacement system of record.
- Appointment, telehealth, messaging, clinical-note, prescribing, billing,
  interoperability, and autonomous AI workflows remain disabled until their
  dedicated product, clinical, legal, and security gates are met.
- The supplied pricing tiers and revenue estimator are hypotheses for
  customer validation, not production billing requirements or verified
  market pricing.

## Phase 2 — patient/provider care relationship

- Provider directory, verified credential workflow, clinician availability,
  patient-approved care relationship, booking/cancellation, idempotency,
  reminders, and scheduling conflict tests.
- Requires clinical operations ownership, jurisdiction and credential
  verification policy, consent language, notification policy, and security
  review.

## Phase 3 — clinical encounters and communication

- Secure async messaging, clinician schedule and patient assignment,
  consultations, encounter notes with draft/signed lifecycle, video-session
  authorization, and follow-up plans.
- Requires clinical workflow review, incident/escalation procedures, retention
  rules, and vendor review for video/messaging.

## Phase 4 — records, integrations, and financial workflows

- Medical document OCR/provenance/review, medication reconciliation,
  prescriptions, laboratory/imaging integrations, payments/insurance, and
  FHIR interoperability.
- Each integration requires data-flow, consent, terminology, audit, vendor,
  and clinical/legal/security approval.

## Release gates

- No production deployment until issuer, client IDs, database, private storage,
  key management, network boundaries, retention, backups/restore, monitoring,
  incident response, and access-review process are configured and tested.
- No real PHI use until a formal privacy/security/legal assessment and
  required agreements are complete. Do not represent this code as HIPAA
  compliant.
- No real clinical consultation, prescribing, or AI clinical decision support
  until appropriate clinical, legal, and security reviews authorize it.

## Four-week implementation roadmap

This delivery advances the foundation into a synthetic-only clinic and
scheduling demonstration. It does not waive the release gates above.

| Week | Delivered foundation | Remaining gate / limitation |
|---|---|---|
| 1 — Architecture | Tenant, patient, provider, location, availability, and appointment data model; auth/PHI boundary and clinic/patient screen wireframes. | Legal/privacy/security release review remains required before real PHI. |
| 2 — Backend foundation | FastAPI/Alembic models and migrations; bearer OIDC validation; tenant membership and role enforcement; atomic audit events; cross-tenant tests. | OIDC issuer/client, PostgreSQL operations, web session, and production controls are deployment configuration. |
| 3 — Clinic portal | Clinic onboarding, single-use staff/provider/patient invitations, patient link creation, location, provider profile, credential verification, and availability API foundations; web screens remain preview-only until browser OIDC sessions are implemented. | No invitation email provider or server-managed web session is configured. |
| 4 — Scheduling | Transactional fixed-slot booking, idempotency, conflict protection, cancellation, rescheduling, privacy-minimal notification outbox, and synthetic API integration tests. | `SCHEDULING_ENABLED` defaults to false; no notification delivery worker exists. Only synthetic demos are authorized. |

The notification outbox is a queue, not evidence that a message was delivered.
The API and UI must not be described as production-ready or HIPAA compliant.
