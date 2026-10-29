"use client";

import { useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type WorkflowAnalytics = {
  documentation: Record<string, number | string>;
  ai_scribe: Record<string, number | string>;
  messaging: Record<string, number | string>;
  care_coordination: Record<string, number | string>;
  ai_operations: Record<string, number | string>;
};

export default function AnalyticsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <AnalyticsView />
    </RoleGate>
  );
}

function AnalyticsView() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [data, setData] = useState<WorkflowAnalytics | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const result = await apiJson<WorkflowAnalytics>(
      `/api/v1/tenants/${tenant_id}/analytics/workflow`,
    );
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setData(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="ANALYTICS"
        title="Clinical workflow analytics"
        description={`${tenant_name} · operational counters from real tenant-scoped events.`}
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />

      <Notice title="Operational metadata only">
        Metrics exclude clinical narrative. AI usage figures are not measures of clinician competence.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}
      {!data && !problem ? <p className="muted">Loading analytics…</p> : null}

      {data ? (
        <>
          <Section title="Documentation">
            <MetricGrid entries={data.documentation} />
          </Section>
          <Section title="AI scribe">
            <MetricGrid entries={data.ai_scribe} />
          </Section>
          <Section title="Patient messaging">
            <MetricGrid entries={data.messaging} />
          </Section>
          <Section title="Care coordination">
            <MetricGrid entries={data.care_coordination} />
          </Section>
          <Section title="AI operations">
            <MetricGrid entries={data.ai_operations} />
          </Section>
        </>
      ) : null}
    </>
  );
}

function MetricGrid({ entries }: { entries: Record<string, number | string> }) {
  return (
    <div className="stat-grid workboard-stats">
      {Object.entries(entries).map(([key, value]) => (
        <div className="stat-tile" key={key}>
          <span className="stat-label">{key.replaceAll("_", " ")}</span>
          <strong className="stat-value">{String(value)}</strong>
        </div>
      ))}
    </div>
  );
}
