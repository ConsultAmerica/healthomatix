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
    title: "Manage your clinic with one readiness-aware workspace",
    body: "Organize clinic information, care team seats, locations, and provider credentials in one place. Onboarding, invitations, and scheduling gates stay explicit—so teams know what is ready and what still needs secure access.",
    objects: ["Clinic Information", "Care Team", "Locations", "Provider Credentials", "Invitations"],
    points: ["Scheduling gates", "Team workflows", "Credential review", "Readiness views"],
    href: "/clinic",
    cta: "Explore clinic demo",
    mock: "clinic-workspace",
    tone: "mint",
  },
  {
    id: "patient",
    label: "Patient portal",
    title: "Connect patients with calm, consent-aware experiences",
    body: "Patient profiles stay masked until identity is ready. Appointment timelines and consent scopes give patients a clear picture of visits and permissions—without inventing live chart access.",
    objects: ["Patient Profile", "Appointments", "Patient Consent", "Medical Records"],
    points: ["Visit overview", "Masked profiles", "Consent scopes", "Family-friendly tone"],
    href: "/patient",
    cta: "Explore patient demo",
    mock: "patient-portal",
    tone: "blue",
  },
  {
    id: "schedule",
    label: "Scheduling board",
    title: "Turn open slots into trustworthy appointments",
    body: "Open slots, booked visits, and booking requests share one board. Idempotency keys and provider/location bindings keep scheduling honest—writes stay gated until authentication is configured.",
    objects: ["Availability", "Appointments", "Booking requests", "Locations"],
    points: ["Open slots", "Confirmed visits", "Idempotent booking", "Timezone-aware"],
    href: "/clinic",
    cta: "See scheduling",
    mock: "scheduling",
    tone: "mint",
  },
  {
    id: "credentials",
    label: "Credential review",
    title: "Keep provider credentials reviewed—never self-verified",
    body: "Credential records track type, jurisdiction, regulator, and status. Review decisions belong to clinic reviewers only, creating a hard scheduling gate before availability can be published.",
    objects: ["Provider Credentials", "Credential submissions", "Review decisions"],
    points: ["Submitted → reviewed", "Jurisdiction aware", "Clinic-only decisions"],
    href: "/clinic",
    cta: "Review credential flow",
    mock: "credentials",
    tone: "ink",
  },
  {
    id: "privacy",
    label: "Privacy & consent",
    title: "Honor access with consent scopes and honest preview limits",
    body: "Consent captures purpose, scope, policy version, and withdrawal. Documents and patient profiles respect those boundaries. Previews show the control plane—not fabricated PHI.",
    objects: ["Patient Consent", "Consent updates", "Medical Records", "Patient Profile"],
    points: ["Purpose + scope", "Policy versions", "Withdrawal ready", "No false live care"],
    href: "#objects",
    cta: "Inspect privacy controls",
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

  return (
    <div
      className="feature-tabs feature-tabs-vertical"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <nav className="feature-tabs-rail" aria-label="Platform features">
        <p className="feature-tabs-rail-label">Capabilities</p>
        <div className="feature-tabs-list" role="tablist" aria-orientation="vertical">
          {tabs.map((tab, index) => (
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
              <span className="feature-tab-num" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="feature-tab-label">{tab.label}</span>
              {tab.id === activeId && rotating ? (
                <span className="feature-tab-progress" aria-hidden="true">
                  <i key={activeId} />
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </nav>

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
              <span key={object} className="feature-chip">{object}</span>
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
