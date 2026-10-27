"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ProductMock, type MockKind } from "./product-mocks";

const tabs: Array<{
  id: string;
  label: string;
  title: string;
  body: string;
  objects: string[];
  points: string[];
  href: string;
  cta: string;
  mock: MockKind;
  tone: string;
}> = [
  {
    id: "clinic",
    label: "Clinic workspace",
    title: "Fuel care teams with a workspace grounded in real clinic objects",
    body: "Seamlessly organize ClinicRead, MemberRead, LocationRead, and CredentialRead in one readiness-aware surface. Onboarding, invitations, and scheduling gates stay explicit—so teams know what is ready and what still needs secure access.",
    objects: ["ClinicRead", "MemberRead", "LocationRead", "CredentialRead", "InvitationRead"],
    points: ["Scheduling gates", "Team workflows", "Credential review", "Readiness views"],
    href: "/clinic",
    cta: "Open clinic preview",
    mock: "clinic-workspace",
    tone: "mint",
  },
  {
    id: "patient",
    label: "Patient portal",
    title: "Deliver calm patient experiences with consent-aware data",
    body: "PatientProfileRead stays masked until identity is ready. AppointmentRead timelines and ConsentRead scopes give patients a clear picture of visits and permissions—without inventing live chart access.",
    objects: ["PatientProfileRead", "AppointmentRead", "ConsentRead", "DocumentRead"],
    points: ["Visit overview", "Masked profiles", "Consent scopes", "Family-friendly tone"],
    href: "/patient",
    cta: "Open patient preview",
    mock: "patient-portal",
    tone: "blue",
  },
  {
    id: "schedule",
    label: "Scheduling board",
    title: "Turn AvailabilityRead slots into trustworthy AppointmentRead visits",
    body: "Open slots, booked visits, and AppointmentCreate payloads share one board. Idempotency keys and provider/location bindings keep scheduling honest—writes stay gated until authentication is configured.",
    objects: ["AvailabilityRead", "AppointmentRead", "AppointmentCreate", "LocationRead"],
    points: ["Open slots", "Confirmed visits", "Idempotent booking", "Timezone-aware"],
    href: "/clinic#schedule",
    cta: "See scheduling gates",
    mock: "scheduling",
    tone: "mint",
  },
  {
    id: "credentials",
    label: "Credential review",
    title: "Keep provider credentials reviewed—never self-verified",
    body: "CredentialRead rows track type, jurisdiction, regulator, and status. CredentialReview decisions belong to clinic reviewers only, creating a hard scheduling gate before AvailabilityWrite is allowed.",
    objects: ["CredentialRead", "CredentialWrite", "CredentialReview"],
    points: ["Submitted → reviewed", "Jurisdiction aware", "Clinic-only decisions"],
    href: "/clinic#providers",
    cta: "Review credential flow",
    mock: "credentials",
    tone: "ink",
  },
  {
    id: "privacy",
    label: "Privacy & consent",
    title: "Honor access with consent scopes and honest preview limits",
    body: "ConsentRead captures purpose, scope, policy version, and withdrawal. DocumentRead and PatientProfileRead respect those boundaries. Previews show the control plane—not fabricated PHI.",
    objects: ["ConsentRead", "ConsentWrite", "DocumentRead", "PatientProfileRead"],
    points: ["Purpose + scope", "Policy versions", "Withdrawal ready", "No false live care"],
    href: "#objects",
    cta: "Inspect privacy objects",
    mock: "privacy-consent",
    tone: "blue",
  },
];

export function FeatureTabs() {
  const [activeId, setActiveId] = useState(tabs[0].id);
  const [auto, setAuto] = useState(true);
  const [hovered, setHovered] = useState(false);
  const activeIndex = tabs.findIndex((tab) => tab.id === activeId);
  const active = tabs[activeIndex] ?? tabs[0];
  const rotating = auto && !hovered;

  useEffect(() => {
    if (!rotating) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      setActiveId((current) => {
        const index = tabs.findIndex((tab) => tab.id === current);
        return tabs[(index + 1) % tabs.length].id;
      });
    }, 6500);
    return () => window.clearInterval(id);
  }, [rotating]);

  function select(id: string) {
    setAuto(false);
    setActiveId(id);
  }

  function move(delta: number) {
    setAuto(false);
    const next = (activeIndex + delta + tabs.length) % tabs.length;
    setActiveId(tabs[next].id);
  }

  return (
    <div
      className="feature-tabs"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="feature-tabs-bar">
        <div className="feature-tabs-controls">
          <button type="button" className="tab-nav-btn" onClick={() => move(-1)} aria-label="Previous feature">
            ←
          </button>
          <button type="button" className="tab-nav-btn" onClick={() => move(1)} aria-label="Next feature">
            →
          </button>
        </div>
        <div className="feature-tabs-list" role="tablist" aria-label="Platform features">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={tab.id === activeId}
              aria-controls={`panel-${tab.id}`}
              className={`feature-tab${tab.id === activeId ? " is-active" : ""}`}
              onClick={() => select(tab.id)}
            >
              {tab.label}
              {tab.id === activeId && rotating ? (
                <span className="feature-tab-progress" aria-hidden="true">
                  <i key={activeId} />
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      <div
        className="feature-tab-layout"
        role="tabpanel"
        id={`panel-${active.id}`}
        aria-labelledby={`tab-${active.id}`}
        key={active.id}
      >
        <div className="feature-tab-copy">
          <p className="feature-tab-index">
            {String(activeIndex + 1).padStart(2, "0")} / {String(tabs.length).padStart(2, "0")}
          </p>
          <h3>{active.title}</h3>
          <p>{active.body}</p>
          <div className="feature-object-row">
            {active.objects.map((object) => (
              <code key={object}>{object}</code>
            ))}
          </div>
          <ul className="feature-point-list">
            {active.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <Link className="text-arrow-link" href={active.href}>
            {active.cta} <span aria-hidden="true">→</span>
          </Link>
        </div>
        <div className={`feature-tab-visual tone-${active.tone}`}>
          <ProductMock kind={active.mock} />
        </div>
      </div>
    </div>
  );
}
