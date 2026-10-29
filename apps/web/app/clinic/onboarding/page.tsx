"use client";

import { useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Task = {
  task_id: string;
  task_code: string;
  task_name: string;
  status: string;
};

type Onboarding = {
  workflow_id: string;
  status: string;
  progress: { completed: number; total: number };
  tasks: Task[];
};

export default function ClinicOnboardingPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff"]}>
      <OnboardingWorkspace />
    </RoleGate>
  );
}

function OnboardingWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [data, setData] = useState<Onboarding | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const res = await apiJson<Onboarding>(`/api/v1/tenants/${tenant_id}/onboarding`);
    if (!res.ok) {
      if (res.problem.code === "ONBOARDING_NOT_FOUND" || res.problem.status === 404) {
        setData(null);
        return;
      }
      setProblem(res.problem);
      return;
    }
    setData(res.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start() {
    const res = await apiJson(`/api/v1/tenants/${tenant_id}/onboarding/start`, { method: "POST" });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function complete(taskId: string) {
    const res = await apiJson(`/api/v1/tenants/${tenant_id}/onboarding/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed" }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function submitReview() {
    const res = await apiJson(`/api/v1/tenants/${tenant_id}/onboarding/submit-review`, {
      method: "POST",
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="ONBOARDING"
        title="Clinic setup checklist"
        description={`${tenant_name} · guided activation readiness (persisted tasks).`}
      />
      <Notice title="Activation" tone="info">
        Completing tasks marks the clinic ready for review. Platform operators approve final activation.
      </Notice>
      {problem ? <FormError problem={problem} /> : null}

      {!data ? (
        <Section title="Start onboarding">
          <EmptyState
            title="Not started"
            description="Begin the checklist to track setup progress for this organization."
          />
          <button className="button" type="button" style={{ marginTop: "1rem" }} onClick={() => void start()}>
            Start onboarding
          </button>
        </Section>
      ) : (
        <Section title={`Status: ${data.status} (${data.progress.completed}/${data.progress.total})`}>
          <ul className="dashboard-list">
            {data.tasks.map((task) => (
              <li key={task.task_id}>
                <div className="list-row">
                  <div>
                    <strong>{task.task_name}</strong>
                    <p className="muted">{task.task_code}</p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={task.status} />
                    {task.status !== "completed" ? (
                      <button
                        className="button button-small"
                        type="button"
                        onClick={() => void complete(task.task_id)}
                      >
                        Mark done
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {data.status === "ready_for_review" ? (
            <button className="button" type="button" style={{ marginTop: "1rem" }} onClick={() => void submitReview()}>
              Confirm ready for review
            </button>
          ) : null}
        </Section>
      )}
    </>
  );
}
