"use client";

import { useState } from "react";

type NodeState = "live" | "planned";

type GraphNode = {
  id: string;
  label: string;
  state: NodeState;
  summary: string;
  standards: string[];
  timeline: string;
  apis: string[];
};

const NODES: GraphNode[] = [
  {
    id: "patient",
    label: "Patients",
    state: "live",
    summary: "Patient portal membership with consent-gated chart views.",
    standards: ["FHIR R4 Patient", "OAuth 2.0 / OIDC"],
    timeline: "Available in preview today",
    apis: ["Patient Profile", "Patient Consent", "Appointments"],
  },
  {
    id: "clinic",
    label: "Clinics",
    state: "live",
    summary: "Tenant-scoped clinic workspace with invites, credentials, and readiness gates.",
    standards: ["FHIR R4 Organization", "OIDC BFF"],
    timeline: "Available in preview today",
    apis: ["Clinic Information", "Invitations", "Provider Credentials"],
  },
  {
    id: "lab",
    label: "Laboratories",
    state: "planned",
    summary: "Outbound lab report exchange once partner onboarding lands.",
    standards: ["HL7 v2 ORU", "FHIR R4 DiagnosticReport", "SMART Backend Services"],
    timeline: "Target: partner pilot after credential + consent gates harden",
    apis: ["Medical Records (lab)", "Lab results write (planned)"],
  },
  {
    id: "pharm",
    label: "Pharmacies",
    state: "planned",
    summary: "ePrescribing and dispense status without implying live pharmacy connectivity yet.",
    standards: ["NCPDP SCRIPT", "FHIR R4 MedicationRequest"],
    timeline: "Target: roadmap edge after laboratory path",
    apis: ["Medication requests (planned)", "Consent scope: medications"],
  },
];

export function CareGraphExplorer() {
  const [selectedId, setSelectedId] = useState("lab");
  const selected = NODES.find((node) => node.id === selectedId) ?? NODES[0];

  return (
    <div className="care-graph-explorer">
      <div className="care-graph" role="group" aria-label="Care network nodes">
        {NODES.map((node) => (
          <button
            key={node.id}
            type="button"
            className={`care-node state-${node.state}${node.id === selected.id ? " is-selected" : ""}`}
            onClick={() => setSelectedId(node.id)}
            aria-pressed={node.id === selected.id}
          >
            <strong>{node.label}</strong>
            <span>{node.state}</span>
          </button>
        ))}
        <svg className="care-edges" viewBox="0 0 400 220" preserveAspectRatio="none" aria-hidden="true">
          <path d="M90 50 C160 50, 160 50, 230 50" />
          <path d="M230 70 C230 120, 90 120, 90 160" />
          <path d="M230 70 C230 120, 310 120, 310 160" />
          <path className="planned" d="M90 180 C180 200, 260 200, 310 180" />
        </svg>
      </div>
      <aside className="care-graph-detail" aria-live="polite">
        <p className="section-kicker">{selected.state === "live" ? "Live preview path" : "Planned edge"}</p>
        <h3>{selected.label}</h3>
        <p>{selected.summary}</p>
        <p className="care-graph-timeline">
          <strong>Timeline:</strong> {selected.timeline}
        </p>
        <div className="care-graph-tags">
          <p className="schema-relations-label">Standards</p>
          <ul>
            {selected.standards.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="care-graph-tags">
          <p className="schema-relations-label">API surface</p>
          <ul>
            {selected.apis.map((item) => (
              <li key={item}>
                <code>{item}</code>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
