"use client";

import { FormEvent, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type ClinicalContext = {
  patient_reference: string;
  encounter_reference: string | null;
  context_status: string;
  observations: Array<{
    observation_reference?: string;
    display?: string;
    verification_status: string;
    source_reference?: string;
  }>;
  evidence: Array<{
    evidence_id: string;
    source_type: string;
    source_resource_id: string;
    verification_status: string;
  }>;
  warnings: string[];
  note: string;
};

export default function ClinicalContextPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <ClinicalContextView />
    </RoleGate>
  );
}

function ClinicalContextView() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [patientId, setPatientId] = useState("");
  const [data, setData] = useState<ClinicalContext | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  async function onLoad(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setData(null);
    const res = await apiJson<ClinicalContext>(
      `/api/v1/tenants/${tenant_id}/patients/${patientId.trim()}/ai/clinical-context`,
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setData(res.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="CLINICAL AI"
        title="Clinical context inspector"
        description={`${tenant_name} · authorized retrieval with verification status and provenance.`}
      />
      <Notice title="Source of truth" tone="warning">
        Context is built from existing FHIR/clinical records. Missing facts stay missing. Unverified imports
        are labeled and never treated as verified labs.
      </Notice>
      {problem ? <FormError problem={problem} /> : null}
      <Section title="Load context">
        <form className="stack-form" onSubmit={(e) => void onLoad(e)}>
          <label>
            Patient user ID
            <input
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              required
              minLength={36}
              maxLength={36}
            />
          </label>
          <button className="button" type="submit">
            Retrieve authorized context
          </button>
        </form>
      </Section>
      {data ? (
        <>
          <Section title="Summary">
            <p>
              Patient {data.patient_reference} · status{" "}
              <StatusBadge status={data.context_status}>{data.context_status}</StatusBadge>
            </p>
            <p className="muted">{data.note}</p>
            {data.warnings.length ? (
              <ul className="dashboard-list">
                {data.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
          </Section>
          <Section title="Observations">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Display</th>
                  <th>Verification</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {data.observations.map((o, idx) => (
                  <tr key={`${o.observation_reference}-${idx}`}>
                    <td>{o.observation_reference || "—"}</td>
                    <td>{o.display || "—"}</td>
                    <td>
                      <StatusBadge status={o.verification_status}>{o.verification_status}</StatusBadge>
                    </td>
                    <td className="muted">{o.source_reference?.slice(0, 8) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
          <Section title="Evidence & provenance">
            <pre className="code-block">{JSON.stringify(data.evidence, null, 2)}</pre>
          </Section>
        </>
      ) : null}
    </>
  );
}
