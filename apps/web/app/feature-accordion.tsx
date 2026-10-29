"use client";

import { useState } from "react";
import { ProductMock, type MockKind } from "./product-mocks";

const items: Array<{
  id: string;
  title: string;
  summary: string;
  detail: string;
  bullets: string[];
  href: string;
  linkLabel: string;
  mock: MockKind;
  tone: string;
}> = [
  {
    id: "clinic",
    title: "Manage Your Clinic",
    summary:
      "Spin up a clinic workspace with onboarding, team invites, credential review, and readiness checks—shaped around how care teams actually operate.",
    detail:
      "Invite staff, verify provider credentials, and see what is ready to schedule. Patient charts stay unavailable until secure sign-in and consent are in place.",
    bullets: [
      "Clinic information & locations",
      "Team invitations",
      "Provider credential review",
    ],
    href: "/clinic",
    linkLabel: "Explore clinic demo",
    mock: "clinic-workspace",
    tone: "mint",
  },
  {
    id: "patient",
    title: "Connect With Your Patients",
    summary:
      "Give patients a calmer portal for visits, documents, and consent-aware summaries—built around clarity, trust, and respectful privacy defaults.",
    detail:
      "Patients see appointments, upload records, and control what the clinic can access. Previews stay honest—no invented live chart access.",
    bullets: [
      "Appointments & visit overview",
      "Medical records upload",
      "Patient consent controls",
    ],
    href: "/patient",
    linkLabel: "Explore patient demo",
    mock: "patient-portal",
    tone: "blue",
  },
  {
    id: "privacy",
    title: "Privacy and readiness you can show",
    summary:
      "Every sensitive surface respects access boundaries. Notices, readiness states, and consent scopes make limitations obvious—never look like live care when they are not.",
    detail:
      "Consent, documents, and credentials each carry explicit access rules. Previews trim what is unavailable instead of inventing live data.",
    bullets: [
      "Consent purpose & scope",
      "Consent-scoped documents",
      "No false live patient data",
    ],
    href: "#objects",
    linkLabel: "Browse developer schemas",
    mock: "privacy-consent",
    tone: "blue",
  },
];

export function FeatureAccordion() {
  const [openId, setOpenId] = useState(items[0].id);
  const active = items.find((item) => item.id === openId) ?? items[0];

  return (
    <div className="feature-accordion">
      <div className="feature-accordion-list">
        {items.map((item) => {
          const open = item.id === openId;
          return (
            <div
              className={`feature-accordion-item${open ? " is-open" : ""}`}
              key={item.id}
            >
              <button
                type="button"
                className="feature-accordion-trigger"
                aria-expanded={open}
                onClick={() => setOpenId(item.id)}
              >
                <span>{item.title}</span>
                <span className="feature-accordion-chevron" aria-hidden="true">
                  <svg viewBox="0 0 20 20" width="18" height="18">
                    <path
                      d={open ? "M5 12l5-5 5 5" : "M7 5l5 5-5 5"}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              </button>
              {open && (
                <div className="feature-accordion-panel">
                  <p>{item.summary}</p>
                  <p className="feature-accordion-detail">{item.detail}</p>
                  <ul className="feature-object-chips">
                    {item.bullets.map((bullet) => (
                      <li key={bullet}><span>{bullet}</span></li>
                    ))}
                  </ul>
                  <a className="text-arrow-link" href={item.href}>
                    {item.linkLabel} <span aria-hidden="true">→</span>
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="feature-accordion-visual">
        <div className={`feature-visual-frame tone-${active.tone}`} key={active.id}>
          <ProductMock kind={active.mock} />
        </div>
      </div>
    </div>
  );
}
