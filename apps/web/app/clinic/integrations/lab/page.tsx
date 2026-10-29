"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Connection = {
  connection_id: string;
  connection_name: string;
  integration_type: string;
  external_system: string;
  status: string;
};

const SAMPLE_ORU =
  "MSH|^~\\&|LAB|SANDBOX|||20260110120000||ORU^R01|MSG-UI-001|P|2.5\r" +
  "PID|1||EXT-PAT-UI^^^SANDBOX||Demo^Patient||19900115\r" +
  "OBR|1|ORD-UI||4548-4^HbA1c\r" +
  "OBX|1|NM|4548-4^HbA1c||5.6|%|4.0-5.6|N|||F|||20260110120000\r";

export default function LabIntegrationPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <LabWorkspace />
    </RoleGate>
  );
}

function LabWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [patientId, setPatientId] = useState("");
  const [message, setMessage] = useState(SAMPLE_ORU);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const res = await apiJson<Connection[]>(`/api/v1/tenants/${tenant_id}/integrations/connections`);
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    const labs = res.data.filter((c) => c.integration_type === "hl7_lab");
    setConnections(labs);
    if (!connectionId && labs[0]) setConnectionId(labs[0].connection_id);
  }, [tenant_id, connectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onIngest(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setResult(null);
    const body: Record<string, string> = {
      connection_id: connectionId,
      message,
    };
    if (patientId.trim()) body.local_patient_id = patientId.trim();
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/hl7/oru`,
      { method: "POST", body: JSON.stringify(body) },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setResult(res.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="LABORATORY"
        title="HL7 result ingest"
        description={`${tenant_name} · sandbox ORU^R01 — identity review before clinical acceptance.`}
        actions={
          <div className="row-actions">
            <Link className="button button-small button-light" href="/clinic/integrations">
              Hub
            </Link>
            <Link className="button button-small" href="/clinic/integrations/identity">
              Identity queue
            </Link>
          </div>
        }
      />

      <Notice title="Not clinical verification" tone="warning">
        Successful parse does not make a laboratory result verified. Imports are marked
        imported_unverified until authorized clinical review.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Laboratory connections">
        {connections.length ? (
          <ul className="dashboard-list">
            {connections.map((conn) => (
              <li key={conn.connection_id}>
                <div className="list-row">
                  <div>
                    <strong>{conn.connection_name}</strong>
                    <p className="muted">{conn.external_system}</p>
                  </div>
                  <StatusBadge status={conn.status} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="No HL7 lab connections"
            description="Create an hl7_lab connection from the Integration hub first."
          />
        )}
      </Section>

      <Section title="Ingest ORU^R01">
        <form className="stack-form" onSubmit={(e) => void onIngest(e)}>
          <label>
            Connection
            <select value={connectionId} onChange={(e) => setConnectionId(e.target.value)} required>
              <option value="">Select…</option>
              {connections.map((c) => (
                <option key={c.connection_id} value={c.connection_id}>
                  {c.connection_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Proposed local patient ID (optional)
            <input
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="Requires manual identity confirmation"
            />
          </label>
          <label>
            Message
            <textarea rows={8} value={message} onChange={(e) => setMessage(e.target.value)} required />
          </label>
          <button className="button" type="submit" disabled={!connectionId}>
            Submit message
          </button>
        </form>
        {result ? (
          <pre className="code-block" style={{ marginTop: "1rem" }}>
            {JSON.stringify(result, null, 2)}
          </pre>
        ) : null}
      </Section>
    </>
  );
}
