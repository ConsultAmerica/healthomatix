"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Org = {
  organization_id: string;
  display_name: string;
  lifecycle_stage: string;
  health_score: number;
  health_factors: Record<string, unknown>;
  onboarding_status: string;
  plan_code: string | null;
  renewal_date: string | null;
};

export default function CustomersPage() {
  const [rows, setRows] = useState<Org[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    const res = await apiJson<Org[]>("/api/v1/platform/customer-success/organizations");
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setRows(res.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="CUSTOMER SUCCESS"
        title="Customer directory"
        description="Explainable commercial health scores — not clinical patient health."
      />
      <Notice title="Not clinical" tone="info">
        Health scores combine onboarding, subscription, support load, and critical incidents using
        documented factors (versioned).
      </Notice>
      {problem ? <FormError problem={problem} /> : null}
      <Section title="Organizations">
        {rows.length ? (
          <ul className="dashboard-list">
            {rows.map((row) => (
              <li key={row.organization_id}>
                <div className="list-row">
                  <div>
                    <strong>{row.display_name}</strong>
                    <p className="muted">
                      {row.lifecycle_stage} · onboarding {row.onboarding_status} · plan{" "}
                      {row.plan_code ?? "none"}
                      {row.renewal_date ? ` · renews ${row.renewal_date}` : ""}
                      <br />
                      Factors: {JSON.stringify(row.health_factors)}
                    </p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={`health-${row.health_score}`} />
                    <strong>{row.health_score}</strong>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No organizations" description="Provisioned tenants appear here." />
        )}
      </Section>
    </>
  );
}
