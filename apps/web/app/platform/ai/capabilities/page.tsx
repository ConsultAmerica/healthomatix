"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Capability = {
  capability_id: string;
  capability_code: string;
  capability_version: string;
  description: string;
  domain: string;
  risk_level: string;
  status: string;
  requires_human_approval: boolean;
  allowed_tools: string[];
};

export default function CapabilityRegistryPage() {
  const [rows, setRows] = useState<Capability[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const res = await apiJson<Capability[]>("/api/v1/platform/ai/capabilities");
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setRows(res.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function advance(cap: Capability, action: "review" | "approve" | "enable") {
    setBusy(cap.capability_id);
    setProblem(null);
    let res;
    if (action === "review") {
      res = await apiJson(`/api/v1/platform/ai/capabilities/${cap.capability_id}/submit-review`, {
        method: "POST",
      });
    } else if (action === "approve") {
      res = await apiJson(`/api/v1/platform/ai/capabilities/${cap.capability_id}/approve`, {
        method: "POST",
      });
    } else {
      res = await apiJson(`/api/v1/platform/ai/capabilities/${cap.capability_id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "enabled" }),
      });
    }
    setBusy(null);
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="V2.1.1"
        title="Agent capability registry"
        description="Versioned capability contracts with lifecycle controls. Extends V2.0 agents — does not replace them."
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />
      <Notice title="Activation policy" tone="info">
        High-risk capabilities start registered and require security review, evaluation, approval, then enable.
        Server enforces permissions independently of declarations.
      </Notice>
      <p>
        <Link href="/platform/ai">← AI command center</Link>
        {" · "}
        <Link href="/platform/ai/readiness">Architecture readiness</Link>
      </p>
      {problem ? <FormError problem={problem} /> : null}
      <Section title="Capabilities">
        <table className="data-table">
          <thead>
            <tr>
              <th>Capability</th>
              <th>Domain</th>
              <th>Version</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Tools</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.capability_id}>
                <td>
                  <strong>{row.capability_code}</strong>
                  <div className="muted">{row.description}</div>
                </td>
                <td>{row.domain}</td>
                <td>{row.capability_version}</td>
                <td>{row.risk_level}</td>
                <td>
                  <StatusBadge status={row.status}>{row.status}</StatusBadge>
                </td>
                <td className="muted">{row.allowed_tools.join(", ") || "—"}</td>
                <td>
                  {row.status === "registered" || row.status === "security_review" ? (
                    <button
                      className="button button-small button-light"
                      type="button"
                      disabled={busy === row.capability_id}
                      onClick={() => void advance(row, "review")}
                    >
                      Submit review
                    </button>
                  ) : null}{" "}
                  {row.status === "evaluation" || row.status === "registered" || row.status === "security_review" ? (
                    <button
                      className="button button-small"
                      type="button"
                      disabled={busy === row.capability_id}
                      onClick={() => void advance(row, "approve")}
                    >
                      Approve
                    </button>
                  ) : null}{" "}
                  {row.status === "approved" ? (
                    <button
                      className="button button-small"
                      type="button"
                      disabled={busy === row.capability_id}
                      onClick={() => void advance(row, "enable")}
                    >
                      Enable
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </>
  );
}
