# Clinic and patient screen wireframes

These wireframes describe the intended responsive screens. The current web
portals are previews, not authenticated production applications. Any
interactive walkthrough uses synthetic-only data and must say when actions are
not persisted or delivered.

## Clinic portal

### Onboarding and workspace

```text
+--------------------------------------------------------------+
| healthomatix.                              CLINIC WORKSPACE   |
+--------------------+-----------------------------------------+
| Overview           | Set up your clinic                     |
| Patients           | [Clinic name________________________]  |
| Providers          | [Location___________] [Timezone______] |
| Availability       | [Create clinic]                         |
| Schedule           |                                         |
| Staff              | Invite a team member                    |
| Settings            | [Email____________] [Role___________]  |
|                    | [Create invitation] [Copy once]         |
|                    |                                         |
|                    | Identity: not configured                |
+--------------------+-----------------------------------------+
```

Onboarding creates a tenant, the authenticated owner's admin membership, and
the initial location. Invitation codes are single-use, expire after seven
days, and are returned once. Codes must be shared securely out-of-band; no
email provider is configured. Patient invitations create a clinic-specific
patient relationship when accepted by an authenticated user.

### Patients and providers

```text
Patients                                      [Invite patient]
Search by clinic chart number or name (future)
No patient names or chart contents are shown until a secure staff session,
tenant membership, and patient relationship are available.

Providers                                     [Invite provider]
Provider | Specialty | Credential state | Profile state
```

Provider profile details and credential verification are separate. Providers
cannot mark their own credentials verified. Patient-facing provider discovery
is not part of this API delivery.

### Availability and schedule

```text
Schedule                     [Week] [<] [>]
Provider: Synthetic Provider · Verified
Location: Main clinic · America/New_York
08:00   Open
08:30   Booked — patient ID hidden in this wireframe
09:00   Open

Outbox: appointment events pending; no notifications have been sent.
```

Availability is stored as timezone-aware 30-minute UTC slots and shown in the
clinic location timezone. The calendar only displays a provider's own
appointments or tenant-wide appointments to an authorized clinic admin/staff
member.

## Patient portal

### Care and booking

```text
+--------------------------------------------------------------+
| healthomatix.                                  PATIENT PORTAL |
+--------------------+-----------------------------------------+
| Home               | Book a clinic appointment               |
| Care               | Clinic: [linked clinic]                  |
| Appointments       | Provider: [verified provider]            |
| Records            | Date: [available dates]                  |
| Messages           | Time: [open slots in clinic timezone]    |
| Profile            | [Review appointment]                     |
|                    |                                           |
|                    | Appointment details                      |
|                    | [Confirm booking]                        |
|                    | [Cancel] [Reschedule]                    |
|                    | Sign-in: not configured                   |
+--------------------+-----------------------------------------+
```

Booking requires an active patient membership and clinic-patient link. The API
rechecks slot state transactionally, enforces idempotency, and only exposes
verified active providers. Cancellation releases a slot; rescheduling locks
the old and new slots in deterministic order.

## Loading, errors, and accessibility

- Show explicit identity/API unavailable, loading, empty, permission denied,
  conflict, and retry states. Never substitute fabricated records for an
  unavailable API response.
- Use semantic headings, labeled inputs, keyboard-accessible controls, visible
  focus, reduced-motion support, and text labels in addition to status colors.
- Keep the clinic/patient role and selected tenant visible. Context changes
  must not imply cross-clinic record sharing.
- The static preview must display a prominent synthetic-data disclaimer and
  must not imply that a local browser action created a real appointment or
  sent a notification.
