"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Claim = {
  claim_id: string;
  claim_number: string;
  status: string;
  total_charge_cents: number;
};

type Denial = {
  denial_id: string;
  claim_id: string;
  denial_code: string;
  denial_category: string;
  denied_amount_cents: number;
  status: string;
};

type RcmAnalytics = {
  overview: Record<string, number>;
  denials: Record<string, number>;
  collections: Record<string, number>;
  notes: string[];
};

export default function RcmPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff"]}>
      <RcmWorkspace />
    </RoleGate>
  );
}

function RcmWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [denials, setDenials] = useState<Denial[]>([]);
  const [analytics, setAnalytics] = useState<RcmAnalytics | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const [claimsRes, denialsRes, analyticsRes] = await Promise.all([
      apiJson<Claim[]>(`/api/v1/tenants/${tenant_id}/claims`),
      apiJson<Denial[]>(`/api/v1/tenants/${tenant_id}/rcm/denials`),
      apiJson<RcmAnalytics>(`/api/v1/tenants/${tenant_id}/analytics/rcm/overview`),
    ]);
    if (!claimsRes.ok) {
      setProblem(claimsRes.problem);
      return;
    }
    if (!denialsRes.ok) {
      setProblem(denialsRes.problem);
      return;
    }
    if (!analyticsRes.ok) {
      setProblem(analyticsRes.problem);
      return;
    }
    setClaims(claimsRes.data);
    setDenials(denialsRes.data);
    setAnalytics(analyticsRes.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="REVENUE CYCLE"
        title="Claims & collections"
        description={`${tenant_name} · sandbox insurance, claims, denials, and remittance posting.`}
        actions={
          <div className="row-actions">
            <button className="button button-small button-light" type="button" onClick={() => void load()}>
              Refresh
            </button>
            <Link className="button button-small button-light" href="/clinic/insurance">
              Insurance
            </Link>
            <Link className="button button-small" href="/clinic/subscription">
              Subscription
            </Link>
          </div>
        }
      />

      <Notice title="Sandbox financials" tone="warning">
        Eligibility does not guarantee payment. Clearinghouse acceptance is not payer payment. No real
        claims or card data are transmitted. Amounts are synthetic cents.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      {analytics ? (
        <div className="stat-grid workboard-stats">
          {Object.entries(analytics.overview).map(([key, value]) => (
            <div className="stat-tile" key={key}>
              <span className="stat-label">{key.replaceAll("_", " ")}</span>
              <strong className="stat-value">{value}</strong>
            </div>
          ))}
        </div>
      ) : null}

      <Section title="Claims work queue">
        {claims.length ? (
          <ul className="dashboard-list">
            {claims.map((claim) => (
              <li key={claim.claim_id}>
                <div>
                  <strong>{claim.claim_number}</strong>
                  <span className="muted">
                    {(claim.total_charge_cents / 100).toFixed(2)} ·{" "}
                    <StatusBadge status={claim.status} />
                  </span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No claims yet">
            Create charges from completed encounters, approve coding, then build claims via API or
            billing workflows.
          </EmptyState>
        )}
      </Section>

      <Section title="Denial queue">
        {denials.length ? (
          <ul className="dashboard-list">
            {denials.map((denial) => (
              <li key={denial.denial_id}>
                <div>
                  <strong>
                    {denial.denial_code} · {denial.denial_category}
                  </strong>
                  <span className="muted">
                    {(denial.denied_amount_cents / 100).toFixed(2)} ·{" "}
                    <StatusBadge status={denial.status} />
                  </span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No open denials" />
        )}
      </Section>

      {analytics?.notes?.length ? (
        <Notice title="Reporting notes">{analytics.notes.join(" ")}</Notice>
      ) : null}
    </>
  );
}
