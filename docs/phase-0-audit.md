# Phase 0 — product and repository audit

## Scope and confidence

This update reviews the current Healthomatix source, documentation, and
configured local checks. It does not inspect or modify MediGuide, production
systems, secrets, local database contents, or application logs. Findings
describe the current source and successful local checks, not production
behavior or regulatory compliance.

The MediGuide observations and reuse matrix below are retained from the earlier
read-only audit; MediGuide was not re-inspected for this update. Healthomatix
remains a separate workspace.

## Current state

| Area | Observed | Assessment |
|---|---|---|
| Workspace | Root npm workspaces include `apps/web`, `apps/mobile`, and `packages/*`; the backend is a separate FastAPI/Alembic project. | The four intended experiences are not equally complete: clinic and patient web routes are previews, mobile is a patient shell, and there is no separate SaaS-admin frontend. |
| Backend | FastAPI mounts OIDC identity, tenant onboarding/memberships, invitations, locations, patient/provider profiles, credentials, consent, document metadata, audit, provider availability, scheduling, platform tenant provisioning, and pending support-access requests. | This is a working foundation, not a complete clinic operating system. Scheduling is feature-gated and authorized only for synthetic demonstrations. |
| Identity and authorization | OIDC bearer validation maps issuer/subject to internal users; tenant membership, roles, patient-clinic links, and platform-admin allowlisting are checked server-side. | Browser OIDC callback/secure session and mobile sign-in/PKCE are not implemented. No real identity provider is configured. |
| Tenancy and records | Tenant, membership, clinic location, clinic-patient link, provider credential, consent, audit, and appointment-related tables are present. Composite constraints protect key tenant relationships. | Patient profile and consent models are still user-keyed rather than fully clinic-chart keyed. PostgreSQL RLS is not configured; production isolation still needs PostgreSQL-specific verification and hardening. |
| Documents and storage | Document metadata is modeled and the `PrivateDocumentStorage` boundary fails closed when unconfigured. Patient document metadata listing exists. | No binary upload/download routes, storage provider, OCR pipeline, or extraction review workflow is operational. |
| Scheduling | Availability, 30-minute appointment booking, idempotency, transactional slot reservation, cancellation/rescheduling, audit events, and a privacy-minimal notification outbox are implemented. | `SCHEDULING_ENABLED` defaults to false. Outbox rows are queued events, not delivered notifications; there is no delivery worker. This is not authorization to conduct real clinical care. |
| Web | Next.js 16 / React 19 / TypeScript web workspace includes clinic and patient preview routes. | No secure browser session or live sign-in. These screens must not be used for live accounts or present planned clinical features as operational. |
| Mobile | Expo SDK 58 / React Native patient shell has Home, Care, Records, Messages, and Profile destinations and an Expo SecureStore adapter boundary. | No sign-in flow or live API use. It is a preview, not a deployable patient-care app. |
| SaaS administration | Restricted platform APIs provision tenants and expose tenant metadata; support requests remain pending and do not grant chart access. | No separate admin UI, subscription billing, usage metering, or support-access approval/grant flow. |
| Clinical and commercial modules | API and architecture documents define future contracts and module boundaries. | Encounters, clinical notes, messaging, video, prescriptions, labs/imaging integrations, care plans, payments, insurance, and FHIR are not mounted/operational. |
| Verification | Backend test suite, API generated-output check, web TypeScript check, and mobile TypeScript check were run for this update. | These checks do not prove PostgreSQL/RLS behavior, browser/native sign-in, deployment, private storage, vendor integration, or production readiness. |

### Validation performed for this update

Commands completed successfully:

- `python -m pytest tests -q` — 29 passed.
- `npm run api:check` — generated OpenAPI TypeScript output is current.
- `npm run web:lint` — web TypeScript check (`tsc --noEmit`) passed.
- `npm run mobile:typecheck` — mobile TypeScript check passed.

No production build, PostgreSQL migration/integration run, browser/native
authentication, deployment, or live service was exercised.

### Current implementation status

The repository has progressed beyond the earlier partial foundation: tenant
onboarding, invitation workflows, provider availability, synthetic scheduling,
platform tenant provisioning, and focused automated tests now exist. It is
still not a completed Phase 1 or production clinical system. The patient
identity/profile representation is not yet a full global-identity plus
clinic-specific chart model; resolve that before expanding chart/document
workflows. The browser and mobile experiences remain preview-only until their
authentication flows are implemented and reviewed.

## Reuse matrix

| MediGuide capability | Decision | Conditions |
|---|---|---|
| Document → page → extracted-field → lab-observation provenance | Reuse as a domain reference; adapt the schema. | Preserve source page, extraction method, review state, and explicit patient confirmation. Add tenant ownership, clinic-patient linkage, and immutable audit trail. |
| Lab normalization and line parsing | Candidate for selective reuse. | Check source licensing, unit handling, locale/date behavior, and tests; move behind a domain service. |
| OCR/PDF page extraction and previews | Candidate for selective reuse. | Keep as an isolated processing adapter; enforce content scanning, file limits, private storage, retention/deletion, and no public object access. |
| Human review/confirmation flow | Reuse the pattern, not the UI implementation. | Distinguish extracted drafts from confirmed health records; never accept client-provided provenance as authoritative. |
| Error/resilience and structured logging patterns | Reuse after review. | Exclude health content and credentials from logs; bound retries and avoid retrying non-idempotent writes. |
| Synthetic fixtures and E2E ideas | Reuse after checking fixture contents. | Use only synthetic data in tests, screenshots, and demos. |
| Existing auth/RBAC/audit/provider verification changes | Treat as design evidence only for now. | The files are part of the dirty MediGuide worktree and have not been validated by this audit; do not copy blindly or alter them. |
| Existing Next.js workspace and brand assets | Do not transplant wholesale. | New patient/clinician information architecture, new visual palette, and safer session handling are required. |
| Legacy chat/orchestration/voice/image-analysis routes | Defer. | No Phase 1 dependency; require endpoint inventory, auth, data-flow, safety, and privacy review before reintroduction. |

## Capabilities found vs. missing

Healthomatix source includes tenant provisioning and membership, invitations,
clinic locations, provider credential states and availability, patient-clinic
links, consent grant/withdrawal, audit events, document metadata, OIDC API
authentication, platform tenant administration, and gated synthetic
scheduling. Automated tests cover these foundations; see validation above.

Not operational: browser or mobile sign-in, private document binary
transfers/OCR, notifications delivery, consultations/video, secure clinical
messaging, encounters/clinical notes, prescriptions, lab/imaging integrations,
follow-up plans, payment/insurance, subscriptions/usage metering, and FHIR.
There is a mobile patient shell and web portal previews, but these are not
authenticated clinical applications. No separate SaaS-admin UI exists.

## Product-boundary update from the supplied product brief

Healthomatix is a B2B clinic operating platform; clinics deliver care and own
clinical decisions. Patients can have relationships with multiple clinics.
The platform should complement existing EHRs initially, not claim to replace
one. Clinic web, patient web, patient mobile, and restricted SaaS
administration are distinct experiences. The requested premium visual system
and primary navigation are design requirements, not evidence of implemented
screens. The supplied pricing and revenue estimates are illustrative
hypotheses, not validated market research.

## Security and privacy review notes

- Scope all Healthomatix data by organization membership and the authenticated
  subject; verify ownership/relationship at every object read/write, not only
  at the navigation layer.
- Prefer OIDC access tokens and server-managed web sessions (HttpOnly,
  Secure, SameSite cookies). The existing browser `localStorage` bearer-token
  pattern is not the proposed design.
- Limit CORS to configured exact trusted origins. Do not copy broad
  `vercel.app`, `workers.dev`, or `pages.dev` origin patterns.
- Keep raw files in private object storage; expose only authorized API
  downloads or short-lived access grants. Fail closed if storage is not
  configured.
- Audit security-sensitive actions with actor, tenant, subject, timestamp,
  request ID, and action only. Do not log document text, diagnoses, credentials,
  tokens, or arbitrary payloads.
- Make consent explicit and versioned, and check purpose/scope/expiry/revocation
  at each applicable data access.
- Do not claim HIPAA compliance. A formal legal, security, operational,
  vendor/BAA, and risk assessment is required before such a claim or production
  handling of regulated data.
- Do not activate real consultation, prescribing, or AI clinical decision
  support without clinical, legal, and security review.
