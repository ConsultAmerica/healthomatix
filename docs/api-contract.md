# Healthomatix API contract

This document distinguishes the existing MediGuide surface from the proposed
Healthomatix contract. MediGuide routes are audit evidence only. Healthomatix
routes are labeled as either implemented or proposed; source presence does not
establish production readiness. OIDC, PostgreSQL, and notification delivery
configuration remain environment-specific.

## Current MediGuide route inventory (static)

| Prefix/route | Purpose |
|---|---|
| `/api/auth/*` | Guest, registration, login, logout, current account. |
| `/api/provider-verification/*` | Patient identity and provider credential review flows in the current local worktree. |
| `/api/documents/v2/*` | Owned documents, upload, processing status, review draft, preview, confirm, delete, explain. |
| `/api/medications/v2/*` | Owned medication label/typed text upload, review and record endpoints. |
| `/api/imaging/*` | Owned studies, report extraction/review, findings, comparison, terminology explanations. |
| `/api/labs/*` | Owned lab test lists, timelines, observations and delete operations. |
| `/api/timeline/*`, `/api/search/*` | User-scoped health timeline and search. |
| `/api/chat*`, `/api/orchestrate`, `/api/transcribe`, `/api/documents/analyze`, `/api/translate`, `/api/speak` | Legacy education, AI, voice, and image-processing routes; no `require_user` dependency appears in their handler signatures. |
| `/api/health`, `/api/system/status`, `/api/knowledge` | Health/status and approved-source information. |

The route inventory is not a claim that all routes work in a deployed
environment. Build/test/runtime verification remains outstanding.

## Healthomatix implementation snapshot (static route declarations)

The following routes are mounted in the Healthomatix API.

| Method | Path | Current source behavior / limitation |
|---|---|---|
| `GET` | `/api/v1/health` | Public liveness response. |
| `GET` | `/api/v1/auth/config` | Reports whether OIDC is configured and whether scheduling is enabled; returns no secrets. |
| `GET` | `/api/v1/me` | Requires bearer OIDC token; provisions internal user and returns active tenant memberships. |
| `POST` | `/api/v1/tenants` | Creates a clinic tenant, initial location, and creator's tenant-admin membership from authenticated identity. |
| `GET` | `/api/v1/tenants/{tenant_id}/providers/me/credentials` | Provider's own submitted credentials and review state; no verification references. |
| `GET` | `/api/v1/tenants/{tenant_id}/provider-credentials?status=` | Tenant-admin credential review queue (default `pending`) with provider display name and specialty. |
| `GET` | `/api/v1/tenants/{tenant_id}/members` | Tenant-admin roster of internal user IDs, roles, and states; no contact details. |
| `GET` | `/api/v1/tenants/{tenant_id}/patients` | Tenant admin/staff roster limited to opaque clinic-patient ID, chart number, status, and creation time; no patient names or profile data. |
| `POST`, `GET` | `/api/v1/tenants/{tenant_id}/invitations` | Tenant admin creates short-lived one-use role invitations; staff may invite patients only. Raw bearer codes are returned only at creation and are not email-bound or delivered by this service. |
| `POST` | `/api/v1/invitations/accept` | Authenticated user accepts an invitation; patient invitations create a tenant-scoped clinic-patient link. |
| `DELETE` | `/api/v1/tenants/{tenant_id}/invitations/{invitation_id}` | Tenant admin revokes a pending invitation. |
| `GET`, `POST` | `/api/v1/tenants/{tenant_id}/locations` | Lists active locations or creates a tenant-scoped location. |
| `GET`, `PUT` | `/api/v1/tenants/{tenant_id}/patients/me` | Patient-role profile currently keyed directly by user, not by a tenant-specific clinic-patient record. |
| `GET`, `PUT` | `/api/v1/tenants/{tenant_id}/providers/me` | Provider-role profile. |
| `POST` | `/api/v1/tenants/{tenant_id}/providers/me/credentials` | Provider submits credential metadata. |
| `POST` | `/api/v1/tenants/{tenant_id}/providers/{provider_user_id}/credentials/{credential_id}/review` | Tenant admin reviews pending credential. |
| `GET`, `POST` | `/api/v1/tenants/{tenant_id}/patients/me/consents` | Lists and grants the current patient's consent. |
| `POST` | `/api/v1/tenants/{tenant_id}/patients/me/consents/{consent_id}/withdraw` | Appends a patient consent withdrawal. |
| `GET` | `/api/v1/tenants/{tenant_id}/documents` | Lists current patient's document metadata; no upload/create/delete handler is mounted. |
| `GET` | `/api/v1/tenants/{tenant_id}/audit-events` | Tenant-admin/auditor list with bounded limit. |
| `GET`, `POST` | `/api/v1/tenants/{tenant_id}/providers/me/availability` | Provider's slots; creation requires active verified provider state and an active tenant location. |
| `GET` | `/api/v1/tenants/{tenant_id}/availability` | Patient's clinic-scoped list of open future slots from verified providers. |
| `POST` | `/api/v1/tenants/{tenant_id}/appointments` | Patient books a 30-minute slot with idempotency protection and transactional slot locking. Disabled unless `SCHEDULING_ENABLED=true`. |
| `GET` | `/api/v1/tenants/{tenant_id}/patients/me/appointments` | Patient's own bookings and cancellation history. |
| `GET` | `/api/v1/tenants/{tenant_id}/appointments` | Provider's own or clinic-admin/staff calendar, bounded by date range. |
| `POST` | `/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/cancel` | Patient cancels own active booking; slot release and audit/outbox writes are atomic. |
| `POST` | `/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/reschedule` | Patient moves own active booking to an open slot transactionally. |
| `GET` | `/api/v1/platform/tenants` | Exact configured platform administrators only; returns bounded tenant metadata, not members or clinical records. |
| `POST` | `/api/v1/platform/tenants` | Platform administrator provisions a tenant, initial location, and an existing user's tenant-admin membership; action is audited. |
| `GET`, `POST` | `/api/v1/platform/support-access-requests` | Platform administrator lists or creates purpose-coded, ticket-bound, time-limited pending requests. Requests do not grant support access. |

The API uses bearer OIDC authentication. The web app's server-managed session
and OIDC callback attach that bearer token through a same-origin proxy. Appointment notifications are queued as
privacy-minimal outbox events; no delivery worker/provider is configured.
Document storage remains unconfigured and fails closed. SaaS billing APIs are
not mounted. The OpenAPI schema and `@healthomatix/api-client` TypeScript
types are generated from mounted FastAPI routes; the shared client can attach
an in-memory bearer token but does not persist credentials.

Invitation codes are bearer secrets. The API does not verify email ownership or
deliver invitation messages; administrators must share codes securely with
the intended recipient.

## Proposed Phase 1 Healthomatix contract

These are target contracts, not a statement that the routes below are mounted
or ready for clinical/production use.

| Method | Path | Authorization | Behavior |
|---|---|---|---|
| `GET` | `/api/v1/health` | Public, non-sensitive | Liveness only; does not expose secret values, PHI, or internal paths. |
| `GET` | `/api/v1/auth/config` | Public, non-sensitive | Reports whether the OIDC integration is configured; never returns client secrets. |
| `GET` | `/api/v1/me` | Authenticated | Resolves OIDC subject to internal user and returns basic account plus active tenant memberships. |
| `GET` | `/api/v1/tenants/{tenant_id}/me` | Active tenant member | Returns current user's membership and role in the tenant. |
| `POST` | `/api/v1/tenants/{tenant_id}/patients` | Authorized clinic staff | Register or link a patient identity to this clinic; duplicate resolution is explicit and audited. |
| `GET`, `PUT` | `/api/v1/tenants/{tenant_id}/patients/me` | Authenticated patient with active clinic-patient link | Read/update the patient-facing profile for this clinic relationship; no cross-clinic chart access. |
| `GET` | `/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}` | Authorized clinic staff and explicit care relationship | Returns only the scoped clinic chart summary; foreign tenant/object IDs are non-disclosing. |
| `GET`, `PUT` | `/api/v1/tenants/{tenant_id}/providers/me` | Provider membership | Read/update provider profile; credential state is separate and cannot be self-set to verified. |
| `GET`, `POST` | `/api/v1/tenants/{tenant_id}/patients/me/consents` | Patient membership | List current user's grants; create a purpose/scope/version grant, recording actor/time and audit in one transaction. |
| `POST` | `/api/v1/tenants/{tenant_id}/patients/me/consents/{consent_id}/withdraw` | Consent subject or explicitly authorized delegate | Append withdrawal; no history rewrite. |
| `GET`, `POST` | `/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents` | Patient or authorized clinic staff; purpose and relationship checked | List/create metadata. Binary transfer requires configured private storage and fails closed otherwise. |
| `GET`, `DELETE` | `/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents/{document_id}` | Object owner or explicit authorized care relationship | Return only authorized metadata or mark deletion/retention state; never disclose cross-tenant existence. |
| `GET` | `/api/v1/tenants/{tenant_id}/audit-events` | Restricted administrative/audit role | No patient-facing access; bounded query and minimal event fields. |

Platform subscriptions and usage metering require separate scoped APIs. SaaS
support access must be time-limited, purpose-bound, and audited; platform
administration alone never authorizes clinical-record reads.

### Shared request/response rules

- IDs are opaque UUIDs; timestamps use timezone-aware RFC 3339 UTC.
- Mutations accept only declared fields (`extra = "forbid"` equivalent).
- Tenant scope is resolved against server-side active membership before any
  clinic, patient relationship, provider, consent, document, or audit lookup.
- A patient can have clinic relationships in multiple tenants. A relationship
  in one tenant grants no access to another tenant's records. Sharing requires
  a separate, explicit, scoped, revocable grant.
- Missing, foreign-tenant, and unauthorized object IDs resolve to a
  non-disclosing `404`; unauthenticated requests return `401`; authenticated
  insufficient-role requests return `403`.
- Invalid state transitions return `409`; invalid input returns `422`;
  unavailable OIDC/storage returns `503` with a stable error code.
- Profile reads and writes are `no-store`; document content is never cached
  publicly.

## Future contracts — not operational

These contracts are reserved for separate design and approval. Phase 1 does
not mount the endpoints or claim that workflows are available.

| Module | Contract outline |
|---|---|
| Provider discovery | `GET /api/v1/tenants/{tenant_id}/providers?specialty=&location=`; returns only active, currently verified profiles. |
| On-demand consultations | `POST /api/v1/tenants/{tenant_id}/consultation-requests`; queue admission and clinical coverage controlled separately. |
| Video | `POST /api/v1/consultations/{id}/video-authorizations`; short-lived participant-scoped authorization only, no raw room token in logs. |
| Secure messaging | `POST /api/v1/tenants/{tenant_id}/threads`, `GET/POST /threads/{id}/messages`; asynchronous, consent-aware, attachment storage private. |
| Encounters/notes | `POST /api/v1/tenants/{tenant_id}/encounters`, draft/update/sign lifecycle; explicit author, signer, timestamps and immutable signed version. |
| Medications | Medication reconciliation and prescription orders only after licensed-clinician, jurisdiction, interaction, and legal workflow review; never a patient self-prescribing endpoint. |
| Labs/imaging | Adapter contracts for orders/results with external source identifiers, provenance, terminology, and reconciliation state. |
| Follow-up | `POST /api/v1/encounters/{id}/follow-up-plans`; reminder delivery is separately consented and opt-out aware. |
| Payments/insurance | Idempotent payment-intent/claim references; no cardholder data stored by Healthomatix. |
| FHIR | Versioned R4 resource mapping and consent/security labels; no direct write-through until interoperability and privacy review. |
