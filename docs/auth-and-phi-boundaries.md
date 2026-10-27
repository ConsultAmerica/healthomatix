# Authentication and PHI boundaries

## Authentication and authorization

- API requests use an OIDC bearer access token. The API validates the HTTPS
  issuer, audience, expiry, signing key, and allowed algorithm before resolving
  `(issuer, subject)` to an internal user.
- The application has no password table. OIDC claims establish identity only;
  tenant roles and active status are resolved from server-side memberships.
- Tenant IDs, patient IDs, and role values supplied by a client are never
  proof of authorization. Patient access also requires an active
  tenant-specific clinic-patient link.
- Provider availability requires an active provider membership, active
  provider profile, and a separately reviewed verified credential.
- Cross-tenant or unlinked patient resources return a non-disclosing not-found
  response. Audit events store opaque subject identifiers and event metadata,
  not request bodies or clinical text.
- The web app implements the OIDC authorization-code flow with PKCE in
  Next.js route handlers (`/auth/login`, `/auth/callback`, `/auth/logout`).
  Tokens are kept in an AES-256-GCM encrypted, HttpOnly, SameSite=Lax session
  cookie and attached server-side by the same-origin `/api/v1/*` proxy; the
  browser never receives a token. State-changing proxy requests require a
  matching `Origin` and the `x-healthomatix-csrf` header. The proxy does not
  forward `/api/v1/platform/*`. This flow has not yet been verified against a
  production identity provider. Do not store tokens in browser local storage
  or add a development authentication bypass.
- Platform administration is separate from tenant roles. It is enabled only
  for exact HTTPS issuer/subject pairs supplied in
  `PLATFORM_ADMIN_IDENTITIES`; a tenant role never grants platform access.
  Platform APIs expose tenant metadata only and do not browse clinical records.
- Support-access records are purpose-coded, ticket-bound, time-limited
  requests that remain pending. They do not grant support access or provide a
  chart/document access path. Approval and any exceptional access workflow
  require a separately reviewed control.
- The mobile shell has no sign-in flow. Any future access token must stay in
  the Expo SecureStore adapter; do not persist bearer tokens in browser
  storage.

## Data boundary

- Real PHI must not be used in development, test fixtures, screenshots, sample
  data, logs, or demo recordings.
- Patient profiles and clinic links are sensitive. Appointment time, clinic,
  provider, and patient association are sensitive scheduling data even when
  the appointment contains no diagnosis or free-text reason.
- The initial platform complements existing systems of record. It does not
  create clinical notes, diagnoses, prescriptions, treatment advice, or
  autonomous triage.
- Document metadata exists, but private binary storage is unconfigured and
  fails closed. No public document URLs or local file storage are permitted.
- Audit and notification outbox rows are payload-minimal. The notification
  outbox contains only tenant, appointment, recipient identity, event type,
  status, and timestamps. A pending row means queued, not delivered.

## Scheduling gate

`SCHEDULING_ENABLED` defaults to `false`. Enabling it exposes authenticated
availability, booking, cancellation, and rescheduling endpoints. Keep it off
outside approved synthetic demonstrations until clinical operations, legal,
privacy, security, notification, and release-readiness reviews are complete.
The gate is not a substitute for production controls.

## Before real-data deployment

Complete and verify OIDC client configuration, browser session/CSRF handling,
PostgreSQL operations and tenant isolation, private storage and key management,
network boundaries, backups/restore, retention, monitoring, incident response,
notification delivery/opt-out policy, access reviews, and required agreements.
Do not claim regulatory compliance from the presence of these controls in code.
