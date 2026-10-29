"use client";

import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type ExportMeta = {
  export_id: string;
  status: string;
  format: string;
  entry_count: number;
  expires_at: string | null;
  note: string;
};

export default function PatientExportPage() {
  return (
    <RoleGate roles={["patient"]}>
      <ExportWorkspace />
    </RoleGate>
  );
}

function ExportWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { state: portalState } = usePortal();
  const userId = portalState.status === "ready" ? portalState.user.user_id : null;
  const [meta, setMeta] = useState<ExportMeta | null>(null);
  const [bundle, setBundle] = useState<Record<string, unknown> | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [busy, setBusy] = useState(false);

  async function requestExport() {
    if (!userId) return;
    setBusy(true);
    setProblem(null);
    setBundle(null);
    const created = await apiJson<ExportMeta>(
      `/api/v1/tenants/${tenant_id}/patients/${userId}/export`,
      { method: "POST" },
    );
    setBusy(false);
    if (!created.ok) {
      setProblem(created.problem);
      return;
    }
    setMeta(created.data);
    const download = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/patients/${userId}/exports/${created.data.export_id}`,
    );
    if (!download.ok) {
      setProblem(download.problem);
      return;
    }
    setBundle(download.data);
  }

  function downloadJson() {
    if (!bundle) return;
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/fhir+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `healthomatix-export-${meta?.export_id ?? "bundle"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        eyebrow="DATA PORTABILITY"
        title="Health data export"
        description={`${tenant_name} · authorized FHIR R4 Bundle of supported records you can access.`}
      />

      <Notice title="Supported scope only" tone="info">
        This is an authorized FHIR Bundle collection — not FHIR Bulk Data ($export). Only records you
        are permitted to access are included. Exports expire after 24 hours.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Request export">
        <p className="muted">
          Categories may include demographics, appointments, encounters, verified and imported
          observations, document metadata, and provenance — when present in your clinic record.
        </p>
        <div className="row-actions" style={{ marginTop: "1rem" }}>
          <button className="button" type="button" disabled={busy} onClick={() => void requestExport()}>
            {busy ? "Preparing…" : "Create FHIR export"}
          </button>
          {bundle ? (
            <button className="button button-light" type="button" onClick={downloadJson}>
              Download JSON
            </button>
          ) : null}
        </div>
        {meta ? (
          <p className="muted" style={{ marginTop: "1rem" }}>
            Status {meta.status} · {meta.entry_count} entries · expires {meta.expires_at ?? "n/a"}
            <br />
            {meta.note}
          </p>
        ) : null}
      </Section>
    </>
  );
}
