"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Overview = {
  environment: string;
  launch_mode: string;
  deployment_version: string;
  launch_state: string;
  note: string;
  open_incidents: number;
  sev1_open: number;
  integration_failed: number;
  jobs_queued: number;
  support_open: number;
  active_subscriptions: number;
  ai_failures_24h: number;
  application_availability: string;
  database_health: string;
};

export default function PlatformCommandCenterPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const res = await apiJson<Overview>("/api/v1/platform/operations/overview");
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setData(res.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="HYPERCARE"
        title="Operations command center"
        description="Synthetic/staging telemetry from durable application tables — not invented production SLAs."
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />

      <Notice title="Launch state" tone="warning">
        V1.8 go/no-go remains NO-GO for real PHI. This dashboard is for authorized platform operators in
        non-production or approved pilot scopes only.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      {data ? (
        <>
          <div className="stat-grid workboard-stats">
            <div className="stat-tile">
              <span className="stat-label">environment</span>
              <strong className="stat-value">{data.environment}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">version</span>
              <strong className="stat-value">{data.deployment_version}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">launch state</span>
              <strong className="stat-value">{data.launch_state}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">open incidents</span>
              <strong className="stat-value">{data.open_incidents}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">SEV-1</span>
              <strong className="stat-value">{data.sev1_open}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">integration failures</span>
              <strong className="stat-value">{data.integration_failed}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">jobs queued</span>
              <strong className="stat-value">{data.jobs_queued}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">support open</span>
              <strong className="stat-value">{data.support_open}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">active subs</span>
              <strong className="stat-value">{data.active_subscriptions}</strong>
            </div>
          </div>

          <Section title="Service health">
            <p className="muted">{data.note}</p>
            <div className="row-actions" style={{ marginTop: "0.75rem" }}>
              <StatusBadge status={data.application_availability} />
              <StatusBadge status={data.database_health} />
              <Link className="button button-small button-light" href="/platform/incidents">
                Incidents
              </Link>
              <Link className="button button-small button-light" href="/platform/customers">
                Customers
              </Link>
              <Link className="button button-small" href="/platform/revenue">
                Revenue
              </Link>
            </div>
          </Section>
        </>
      ) : null}
    </>
  );
}
