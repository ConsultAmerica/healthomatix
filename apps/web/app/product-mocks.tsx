/** Product UI mock surfaces — sample domain objects shaped like live API reads. */

import type { ReactNode } from "react";

type MockKind =
  | "clinic-workspace"
  | "patient-portal"
  | "care-graph"
  | "privacy-consent"
  | "scheduling"
  | "credentials";

export function ProductMock({ kind }: { kind: MockKind }) {
  switch (kind) {
    case "clinic-workspace":
      return <ClinicWorkspaceMock />;
    case "patient-portal":
      return <PatientPortalMock />;
    case "care-graph":
      return <CareGraphMock />;
    case "privacy-consent":
      return <PrivacyConsentMock />;
    case "scheduling":
      return <SchedulingMock />;
    case "credentials":
      return <CredentialsMock />;
    default:
      return null;
  }
}

function MockShell({
  title,
  subtitle,
  children,
  tone = "mint",
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  tone?: "mint" | "blue" | "ink";
}) {
  return (
    <div className={`product-mock tone-${tone}`} aria-hidden="true">
      <div className="product-mock-chrome">
        <span className="mock-dots">
          <i /><i /><i />
        </span>
        <span className="mock-title">{title}</span>
        <span className="mock-live">
          <i /> live-shaped
        </span>
        <span className="mock-pill">PREVIEW</span>
      </div>
      <div className="product-mock-body">
        <p className="mock-subtitle">{subtitle}</p>
        {children}
      </div>
      <div className="mock-scanline" />
    </div>
  );
}

function ClinicWorkspaceMock() {
  return (
    <MockShell title="clinic.healthomatix" subtitle="ClinicRead · readiness board" tone="mint">
      <div className="mock-object-card">
        <div className="mock-object-head">
          <strong>ClinicRead</strong>
          <span className="mock-status ok">active</span>
        </div>
        <dl className="mock-fields">
          <div><dt>display_name</dt><dd>Northside Family Care</dd></div>
          <div><dt>slug</dt><dd>northside-family</dd></div>
          <div><dt>location_name</dt><dd>Main Street Clinic</dd></div>
          <div><dt>timezone</dt><dd>America/Toronto</dd></div>
          <div><dt>role</dt><dd>clinic_admin</dd></div>
          <div><dt>tenant_id</dt><dd>tn_8f2a…c41</dd></div>
        </dl>
      </div>
      <div className="mock-row">
        <article className="mock-mini-card">
          <span>MemberRead</span>
          <strong>12</strong>
          <small>team members</small>
        </article>
        <article className="mock-mini-card">
          <span>ClinicPatientRead</span>
          <strong>—</strong>
          <small>sign-in required</small>
        </article>
        <article className="mock-mini-card accent">
          <span>CredentialRead</span>
          <strong>3</strong>
          <small>pending review</small>
        </article>
      </div>
      <div className="mock-chat-float">
        <p className="mock-chat-label">Workspace notice</p>
        <p>Secure browser sign-in is not configured. Live clinic actions stay unavailable.</p>
      </div>
    </MockShell>
  );
}

function PatientPortalMock() {
  return (
    <MockShell title="patient.healthomatix" subtitle="PatientProfileRead · visit overview" tone="blue">
      <div className="mock-split">
        <div className="mock-object-card">
          <div className="mock-object-head">
            <strong>PatientProfileRead</strong>
            <span className="mock-status muted">masked</span>
          </div>
          <dl className="mock-fields">
            <div><dt>preferred_name</dt><dd>••••••</dd></div>
            <div><dt>date_of_birth</dt><dd>••••-••-••</dd></div>
            <div><dt>phone</dt><dd>•••-•••-••••</dd></div>
            <div><dt>locale</dt><dd>en-CA</dd></div>
          </dl>
        </div>
        <div className="mock-timeline">
          <p className="mock-timeline-label">AppointmentRead</p>
          {[
            { when: "Thu 10:30", who: "Dr. Patel", status: "scheduled" },
            { when: "Mon 14:00", who: "Lab follow-up", status: "planned" },
          ].map((item) => (
            <div className="mock-timeline-item" key={item.when}>
              <span>{item.when}</span>
              <strong>{item.who}</strong>
              <em>{item.status}</em>
            </div>
          ))}
        </div>
      </div>
      <div className="mock-consent-bar">
        <span>ConsentRead</span>
        <strong>scope: visit_summary</strong>
        <span className="mock-status ok">granted</span>
      </div>
    </MockShell>
  );
}

function CareGraphMock() {
  const nodes = [
    { id: "patient", label: "Patients", state: "live" },
    { id: "clinic", label: "Clinics", state: "live" },
    { id: "lab", label: "Laboratories", state: "planned" },
    { id: "pharm", label: "Pharmacies", state: "planned" },
  ];
  return (
    <MockShell title="connections.map" subtitle="Care graph · role edges" tone="ink">
      <div className="care-graph">
        {nodes.map((node) => (
          <div className={`care-node state-${node.state}`} key={node.id}>
            <strong>{node.label}</strong>
            <span>{node.state}</span>
          </div>
        ))}
        <svg className="care-edges" viewBox="0 0 400 220" preserveAspectRatio="none">
          <path d="M90 50 C160 50, 160 50, 230 50" />
          <path d="M230 70 C230 120, 90 120, 90 160" />
          <path d="M230 70 C230 120, 310 120, 310 160" />
          <path className="planned" d="M90 180 C180 200, 260 200, 310 180" />
        </svg>
      </div>
      <div className="mock-row">
        <article className="mock-mini-card">
          <span>InvitationRead</span>
          <strong>codes</strong>
          <small>single-use join</small>
        </article>
        <article className="mock-mini-card">
          <span>MembershipRead</span>
          <strong>roles</strong>
          <small>clinic · patient</small>
        </article>
      </div>
    </MockShell>
  );
}

function PrivacyConsentMock() {
  return (
    <MockShell title="privacy.controls" subtitle="ConsentRead · access trimming" tone="blue">
      <div className="mock-object-card">
        <div className="mock-object-head">
          <strong>ConsentRead</strong>
          <span className="mock-status ok">policy v2.1</span>
        </div>
        <dl className="mock-fields">
          <div><dt>purpose</dt><dd>care_coordination</dd></div>
          <div><dt>scope</dt><dd>visit_summary · schedule</dd></div>
          <div><dt>granted_at</dt><dd>2026-10-12T14:22Z</dd></div>
          <div><dt>expires_at</dt><dd>null</dd></div>
          <div><dt>withdrawn_at</dt><dd>null</dd></div>
        </dl>
      </div>
      <div className="mock-acl-list">
        {[
          { resource: "AppointmentRead", access: "owner + clinic_staff" },
          { resource: "PatientProfileRead", access: "owner only" },
          { resource: "DocumentRead", access: "consent-scoped" },
          { resource: "CredentialRead", access: "clinic_reviewer" },
        ].map((row) => (
          <div className="mock-acl-row" key={row.resource}>
            <code>{row.resource}</code>
            <span>{row.access}</span>
          </div>
        ))}
      </div>
    </MockShell>
  );
}

function SchedulingMock() {
  return (
    <MockShell title="schedule.board" subtitle="AvailabilityRead · AppointmentRead" tone="mint">
      <div className="mock-schedule">
        {["09:00", "10:30", "13:00", "15:30"].map((slot, index) => (
          <div className={`mock-slot${index === 1 ? " booked" : ""}`} key={slot}>
            <span>{slot}</span>
            <strong>{index === 1 ? "AppointmentRead" : "AvailabilityRead"}</strong>
            <em>{index === 1 ? "confirmed · Dr. Chen" : "open · Main Street"}</em>
          </div>
        ))}
      </div>
      <div className="mock-object-card compact">
        <div className="mock-object-head">
          <strong>AppointmentCreate</strong>
          <span className="mock-status muted">gated</span>
        </div>
        <dl className="mock-fields">
          <div><dt>availability_id</dt><dd>av_91c…e2</dd></div>
          <div><dt>idempotency_key</dt><dd>req_7b…</dd></div>
        </dl>
      </div>
    </MockShell>
  );
}

function CredentialsMock() {
  return (
    <MockShell title="credentials.review" subtitle="CredentialRead · review gate" tone="ink">
      <div className="mock-row stacked">
        {[
          { type: "medical_license", status: "reviewed", jurisdiction: "ON" },
          { type: "board_cert", status: "submitted", jurisdiction: "CA" },
          { type: "dea_number", status: "pending", jurisdiction: "—" },
        ].map((cred) => (
          <div className="mock-cred-row" key={cred.type}>
            <div>
              <strong>CredentialRead</strong>
              <span>{cred.type}</span>
            </div>
            <em>{cred.jurisdiction}</em>
            <span className={`mock-status ${cred.status === "reviewed" ? "ok" : "muted"}`}>
              {cred.status}
            </span>
          </div>
        ))}
      </div>
      <p className="mock-footnote">Providers cannot verify their own credentials. CredentialReview is clinic-only.</p>
    </MockShell>
  );
}

export type { MockKind };
