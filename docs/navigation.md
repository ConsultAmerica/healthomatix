# Healthomatix navigation and interaction contract

## Clinic web portal

- Primary clinician navigation: **Dashboard**, **Schedule**, **Patients**,
  **Consultations**, **Messages**, **Clinical Notes**.
- Clinic staff additionally need tenant-scoped **Locations**, **Staff**,
  **Services**, and **Settings** areas as those workflows become operational.
- Initial screens expose identity, membership, provider profile, and
  credential-review state. Clinic onboarding/invitations and availability
  APIs exist and the web portal uses them through the signed-in session.
  Navigation is filtered by the active clinic role, and every page also checks
  the role before rendering.
- Scheduling API routes exist behind `SCHEDULING_ENABLED=false` by default.
  Only synthetic API tests/demos are authorized until clinical, legal,
  security, and operational gates pass. Consultation, messaging, and notes
  remain unavailable.
- A staff or provider role alone never grants access to a patient's chart.
  Access requires the same active tenant, a clinic-patient relationship, and
  an explicitly authorized care relationship.

## Patient application

- Primary: **Home**, **Care**, **Records**, **Messages**, **Profile**.
- Home: account/consent status and supported Phase 1 actions. Future scheduling,
  follow-up, and message cards must be labelled unavailable/planned until
  their APIs are implemented.
- Care: current clinic relationship and provider directory entry point;
  booking is disabled unless the backend feature gate, verified provider, and
  patient authorization are all active. Consultation remains unavailable.
- Records: document metadata and review status; actual upload/download is
  disabled until private storage is configured. No fabricated record entries.
- Messages: disabled future module with no fake conversation or send control.
- Profile: patient profile and consent history/revocation, if the identity
  provider and tenant membership are configured.
- A patient can be linked to more than one clinic. Switching clinics changes
  the tenant context; it does not share records between clinics. Cross-clinic
  access must be a separate, explicit, revocable consent/access grant.

## SaaS administration

- Separate, restricted surface for tenant provisioning, subscription status,
  operational health, support requests, and security/audit workflows.
- SaaS administrators receive no implicit patient-chart or document access.
  Any exceptional support access must be scoped, time-limited, purpose-bound,
  approved, and audited.

## Patient web portal

The browser portal supports the patient mobile information architecture,
optimized for document review and form completion. It uses the server-managed
session described in [Authentication and PHI boundaries](./auth-and-phi-boundaries.md).
The browser must not persist bearer tokens in local storage; only the selected
clinic ID is remembered locally.

## Responsive and accessibility requirements

- Mobile-first layouts with responsive side/bottom navigation, visible page
  title and current role.
- Warm ivory canvas; aubergine primary surfaces and text; restrained
  champagne-gold accents. Use color plus text/icon for status.
- Semantic landmarks and headings; keyboard-visible focus; labels and
  descriptions on every input; error summary and inline validation.
- 44px minimum touch targets, adequate contrast, reduced-motion support, and
  no status communicated by color alone.
- Loading, empty, permission-denied, configuration-unavailable, offline, and
  retry states are distinct. Never render synthetic or placeholder records as
  real patient data.
