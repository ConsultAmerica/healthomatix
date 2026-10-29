"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime } from "@/lib/time";

type CareTask = {
  task_id: string;
  description: string;
  task_category: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
};

export default function CareTasksPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [tasks, setTasks] = useState<CareTask[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    setProblem(null);
    const result = await apiJson<CareTask[]>(
      `/api/v1/tenants/${tenant_id}/patients/me/care-tasks`,
    );
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setTasks(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function complete(taskId: string) {
    setPending(true);
    const result = await apiJson<CareTask>(`/api/v1/tenants/${tenant_id}/care-tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed" }),
    });
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="FOLLOW-UP"
        title="Care activities"
        description={`Approved follow-up tasks from ${tenant_name}.`}
        actions={
          <Link className="button button-small button-light" href="/patient/visit-summary">
            Visit summaries
          </Link>
        }
      />

      <Notice title="Clinician-approved only">
        Tasks appear after your care team approves a follow-up plan. Contact the clinic if something
        looks incorrect.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      {!tasks.length ? (
        <EmptyState title="No open care tasks">
          Approved activities will show here after your visit.
        </EmptyState>
      ) : (
        <ul className="dashboard-list">
          {tasks.map((task) => (
            <li key={task.task_id}>
              <div>
                <strong>{task.description}</strong>
                <span className="muted">
                  {task.task_category} · {formatDateTime(task.created_at)} ·{" "}
                  <StatusBadge status={task.status} />
                </span>
              </div>
              {task.status !== "completed" ? (
                <button
                  className="button button-small"
                  type="button"
                  disabled={pending}
                  onClick={() => void complete(task.task_id)}
                >
                  Mark complete
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
