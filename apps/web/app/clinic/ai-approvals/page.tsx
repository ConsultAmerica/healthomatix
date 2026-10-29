"use client";

import { useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Approval = {
  approval_id: string;
  agent_run_id: string;
  status: string;
  required_role: string;
  proposal_version: number;
  proposal_hash: string;
  proposal_payload: Record<string, unknown>;
  expires_at: string | null;
};

export default function AiApprovalsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <AiApprovalsView />
    </RoleGate>
  );
}

function AiApprovalsView() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [rows, setRows] = useState<Approval[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const result = await apiJson<Approval[]>(`/api/v1/tenants/${tenant_id}/ai/approvals`);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setRows(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(approvalId: string, approve: boolean) {
    setBusy(approvalId);
    setProblem(null);
    const path = approve ? "approve" : "reject";
    const result = await apiJson<{ approval_id: string; status: string }>(
      `/api/v1/tenants/${tenant_id}/ai/approvals/${approvalId}/${path}`,
      {
        method: "POST",
        body: JSON.stringify({
          reason: approve ? "Reviewed in clinic approval center" : "Rejected in clinic approval center",
        }),
      },
    );
    setBusy(null);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    await load();
  }

  const pending = rows.filter((r) => r.status === "pending");

  return (
    <>
      <PageHeader
        eyebrow="AI GOVERNANCE"
        title="Human approval center"
        description={`${tenant_name} · review immutable agent proposals before any high-impact action.`}
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />

      <Notice title="Proposal integrity" tone="warning">
        Approvals are bound to a canonical payload hash. Tampered proposals cannot execute. Agents never
        diagnose, prescribe, sign notes, submit claims, or issue refunds on their own.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title={`Pending (${pending.length})`}>
        {pending.length === 0 ? (
          <p className="muted">No pending agent proposals.</p>
        ) : (
          <ul className="dashboard-list">
            {pending.map((row) => (
              <li key={row.approval_id}>
                <div>
                  <StatusBadge status="pending">pending</StatusBadge>{" "}
                  <strong>{String(row.proposal_payload.tool || "proposal")}</strong>
                  <p className="muted">
                    role {row.required_role} · run {row.agent_run_id.slice(0, 8)}… · v
                    {row.proposal_version} · hash {row.proposal_hash.slice(0, 12)}…
                  </p>
                  <pre className="code-block">{JSON.stringify(row.proposal_payload, null, 2)}</pre>
                  <p>
                    <button
                      className="button button-small"
                      type="button"
                      disabled={busy === row.approval_id}
                      onClick={() => void decide(row.approval_id, true)}
                    >
                      Approve
                    </button>{" "}
                    <button
                      className="button button-small button-light"
                      type="button"
                      disabled={busy === row.approval_id}
                      onClick={() => void decide(row.approval_id, false)}
                    >
                      Reject
                    </button>
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Recent decisions">
        <table className="data-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Tool</th>
              <th>Role</th>
              <th>Expires</th>
            </tr>
          </thead>
          <tbody>
            {rows
              .filter((r) => r.status !== "pending")
              .slice(0, 20)
              .map((row) => (
                <tr key={row.approval_id}>
                  <td>
                    <StatusBadge status={row.status}>{row.status}</StatusBadge>
                  </td>
                  <td>{String(row.proposal_payload.tool || "—")}</td>
                  <td>{row.required_role}</td>
                  <td>{row.expires_at ? row.expires_at.slice(0, 19) : "—"}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </Section>
    </>
  );
}
