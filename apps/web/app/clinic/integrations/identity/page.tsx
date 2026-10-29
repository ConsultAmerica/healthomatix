"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Match = {
  link_id: string;
  patient_id: string | null;
  external_system: string;
  external_identifier: string;
  verification_status: string;
  match_evidence: Record<string, unknown>;
};

type Mapping = {
  mapping_id: string;
  source_system: string;
  source_code: string;
  source_display: string;
  target_system: string;
  target_code: string;
  status: string;
};

export default function IdentityPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <IdentityWorkspace />
    </RoleGate>
  );
}

function IdentityWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [matches, setMatches] = useState<Match[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [patientId, setPatientId] = useState("");
  const [sourceCode, setSourceCode] = useState("4548-4");
  const [targetCode, setTargetCode] = useState("4548-4");
  const [sourceSystem, setSourceSystem] = useState("FakeLab");
  const [ehrConnectionId, setEhrConnectionId] = useState("");
  const [importPatientId, setImportPatientId] = useState("");
  const [importResult, setImportResult] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const [matchRes, mapRes, connRes] = await Promise.all([
      apiJson<Match[]>(`/api/v1/tenants/${tenant_id}/integrations/patient-matches`),
      apiJson<Mapping[]>(`/api/v1/tenants/${tenant_id}/integrations/terminology/mappings`),
      apiJson<{ connection_id: string; integration_type: string; connection_name: string }[]>(
        `/api/v1/tenants/${tenant_id}/integrations/connections`,
      ),
    ]);
    if (!matchRes.ok) {
      setProblem(matchRes.problem);
      return;
    }
    if (!mapRes.ok) {
      setProblem(mapRes.problem);
      return;
    }
    setMatches(matchRes.data);
    setMappings(mapRes.data);
    if (connRes.ok) {
      const ehr = connRes.data.find((c) => c.integration_type === "fhir_ehr");
      if (ehr && !ehrConnectionId) setEhrConnectionId(ehr.connection_id);
    }
  }, [tenant_id, ehrConnectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(linkId: string, status: "confirmed" | "rejected") {
    setProblem(null);
    if (status === "confirmed" && !patientId.trim()) {
      setProblem({
        kind: "api",
        status: 400,
        code: "PATIENT_REQUIRED",
        message: "Enter the local patient ID before confirming a match.",
        requestId: "",
        fields: {},
      });
      return;
    }
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/patient-matches/${linkId}/resolve`,
      {
        method: "POST",
        body: JSON.stringify({
          patient_id: patientId.trim() || "00000000-0000-4000-8000-000000000000",
          verification_status: status,
        }),
      },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function onMapping(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    const created = await apiJson<{ mapping_id: string }>(
      `/api/v1/tenants/${tenant_id}/integrations/terminology/mappings`,
      {
        method: "POST",
        body: JSON.stringify({
          source_system: sourceSystem.trim(),
          source_code: sourceCode.trim(),
          source_display: sourceCode.trim(),
          target_system: "http://loinc.org",
          target_code: targetCode.trim(),
        }),
      },
    );
    if (!created.ok) {
      setProblem(created.problem);
      return;
    }
    await load();
  }

  async function approveMapping(mappingId: string) {
    setProblem(null);
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/terminology/mappings/${mappingId}/approve`,
      { method: "POST" },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function onImportPreview(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setImportResult(null);
    const preview = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/imports`,
      {
        method: "POST",
        body: JSON.stringify({
          connection_id: ehrConnectionId,
          patient_family: "Demo",
          local_patient_id: importPatientId.trim(),
        }),
      },
    );
    if (!preview.ok) {
      setProblem(preview.problem);
      return;
    }
    setImportResult(preview.data);
  }

  async function approveImport(batchId: string) {
    setProblem(null);
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/imports/${batchId}/approve`,
      { method: "POST" },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setImportResult(res.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="IDENTITY & TERMINOLOGY"
        title="Patient matching"
        description={`${tenant_name} · manual confirmation required — no automatic merges.`}
        actions={
          <Link className="button button-small button-light" href="/clinic/integrations">
            Integration hub
          </Link>
        }
      />

      <Notice title="Identity safety" tone="warning">
        Name and date of birth alone never auto-merge patients. AI cannot confirm matches or approve
        terminology as clinical fact.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Pending identity reviews">
        <label>
          Local patient ID for confirmation
          <input value={patientId} onChange={(e) => setPatientId(e.target.value)} />
        </label>
        {matches.length ? (
          <ul className="dashboard-list">
            {matches.map((match) => (
              <li key={match.link_id}>
                <div className="list-row">
                  <div>
                    <strong>
                      {match.external_system} / {match.external_identifier}
                    </strong>
                    <p className="muted">{JSON.stringify(match.match_evidence)}</p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={match.verification_status} />
                    <button
                      className="button button-small"
                      type="button"
                      onClick={() => void resolve(match.link_id, "confirmed")}
                    >
                      Confirm
                    </button>
                    <button
                      className="button button-small button-light"
                      type="button"
                      onClick={() => void resolve(match.link_id, "rejected")}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No pending matches" description="Identity conflicts from inbound messages appear here." />
        )}
      </Section>

      <Section title="Terminology mappings">
        <form className="stack-form" onSubmit={(e) => void onMapping(e)}>
          <label>
            Source system
            <input value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} />
          </label>
          <label>
            Source code
            <input value={sourceCode} onChange={(e) => setSourceCode(e.target.value)} />
          </label>
          <label>
            Target LOINC
            <input value={targetCode} onChange={(e) => setTargetCode(e.target.value)} />
          </label>
          <button className="button" type="submit">
            Propose mapping
          </button>
        </form>
        {mappings.length ? (
          <ul className="dashboard-list">
            {mappings.map((row) => (
              <li key={row.mapping_id}>
                <div className="list-row">
                  <div>
                    <strong>
                      {row.source_code} → {row.target_code}
                    </strong>
                    <p className="muted">
                      {row.source_system} · {row.target_system}
                    </p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={row.status} />
                    {row.status === "pending_review" ? (
                      <button
                        className="button button-small"
                        type="button"
                        onClick={() => void approveMapping(row.mapping_id)}
                      >
                        Approve
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>

      <Section title="Clinical import review">
        <form className="stack-form" onSubmit={(e) => void onImportPreview(e)}>
          <label>
            EHR connection ID
            <input value={ehrConnectionId} onChange={(e) => setEhrConnectionId(e.target.value)} required />
          </label>
          <label>
            Local patient ID
            <input value={importPatientId} onChange={(e) => setImportPatientId(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Preview EHR import
          </button>
        </form>
        {importResult ? (
          <>
            <pre className="code-block" style={{ marginTop: "1rem" }}>
              {JSON.stringify(importResult, null, 2)}
            </pre>
            {typeof importResult.batch_id === "string" && importResult.status === "preview" ? (
              <button
                className="button"
                type="button"
                style={{ marginTop: "0.75rem" }}
                onClick={() => void approveImport(importResult.batch_id as string)}
              >
                Approve import
              </button>
            ) : null}
          </>
        ) : null}
      </Section>
    </>
  );
}
