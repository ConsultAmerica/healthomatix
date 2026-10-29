"use client";

import { useCallback, useEffect, useState } from "react";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Revenue = {
  mrr_cents: number;
  arr_cents: number;
  active_subscriptions: number;
  trial_subscriptions: number;
  cancelled_subscriptions: number;
  mrr_by_plan_cents: Record<string, number>;
  methodology: Record<string, string>;
};

export default function RevenuePage() {
  const [data, setData] = useState<Revenue | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    const res = await apiJson<Revenue>("/api/v1/platform/analytics/revenue");
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
        eyebrow="SAAS REVENUE"
        title="Subscription intelligence"
        description="Separate from clinic patient billing / insurance RCM."
      />
      <Notice title="Sandbox methodology" tone="warning">
        MRR uses documented PLAN_MRR_CENTS against active subscriptions — not live processor settlement.
      </Notice>
      {problem ? <FormError problem={problem} /> : null}
      {data ? (
        <>
          <div className="stat-grid workboard-stats">
            <div className="stat-tile">
              <span className="stat-label">MRR</span>
              <strong className="stat-value">${(data.mrr_cents / 100).toFixed(2)}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">ARR</span>
              <strong className="stat-value">${(data.arr_cents / 100).toFixed(2)}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">active</span>
              <strong className="stat-value">{data.active_subscriptions}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">trial</span>
              <strong className="stat-value">{data.trial_subscriptions}</strong>
            </div>
            <div className="stat-tile">
              <span className="stat-label">cancelled</span>
              <strong className="stat-value">{data.cancelled_subscriptions}</strong>
            </div>
          </div>
          <Section title="Methodology">
            <pre className="code-block">{JSON.stringify(data.methodology, null, 2)}</pre>
            <pre className="code-block" style={{ marginTop: "1rem" }}>
              {JSON.stringify(data.mrr_by_plan_cents, null, 2)}
            </pre>
          </Section>
        </>
      ) : null}
    </>
  );
}
