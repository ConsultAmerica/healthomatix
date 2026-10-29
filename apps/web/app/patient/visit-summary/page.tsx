"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime } from "@/lib/time";

type FollowUpPlan = {
  plan_id: string;
  status: string;
  instructions: string;
  tasks: Array<{ description?: string; status?: string }>;
  published_at?: string | null;
};

export default function VisitSummaryPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [plans, setPlans] = useState<FollowUpPlan[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      const result = await apiJson<FollowUpPlan[]>(
        `/api/v1/tenants/${tenant_id}/patients/me/follow-up-plans`,
      );
      setLoading(false);
      if (!result.ok) {
        setProblem(result.problem);
        return;
      }
      setPlans(result.data);
    })();
  }, [tenant_id]);

  return (
    <>
      <PageHeader
        eyebrow="VISIT SUMMARY"
        title="Approved follow-up"
        description={`Clinician-published instructions from ${tenant_name}. Draft AI notes never appear here.`}
        actions={
          <Link className="button button-small button-light" href="/patient/waiting-room">
            Waiting room
          </Link>
        }
      />

      <Notice title="Clinician-approved only">
        You only see follow-up plans after a provider approves and publishes them. Unfinished clinical
        notes and AI drafts stay private to the care team.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}
      {loading ? <p className="muted">Loading summaries…</p> : null}

      {!loading && !plans.length ? (
        <EmptyState title="No published follow-up plans yet">
          After your visit, approved instructions will appear here.
        </EmptyState>
      ) : null}

      <ul className="dashboard-list">
        {plans.map((plan) => (
          <li key={plan.plan_id}>
            <div>
              <strong>Follow-up plan</strong>
              <span className="muted">
                {plan.published_at ? formatDateTime(plan.published_at) : "Published"} ·{" "}
                <StatusBadge status={plan.status} />
              </span>
              <p style={{ margin: "8px 0 0" }}>{plan.instructions || "No instructions recorded."}</p>
              {plan.tasks?.length ? (
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {plan.tasks.map((task, index) => (
                    <li key={`${plan.plan_id}-${index}`}>{task.description || "Care task"}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
