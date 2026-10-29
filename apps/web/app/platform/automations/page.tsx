"use client";

import { useCallback, useEffect, useState } from "react";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Rule = {
  rule_id: string;
  rule_code: string;
  trigger_type: string;
  action_type: string;
  enabled: boolean;
  approval_required: boolean;
};

export default function AutomationsPage() {
  const [rows, setRows] = useState<Rule[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    const res = await apiJson<Rule[]>("/api/v1/platform/automations");
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
      <PageHeader eyebrow="AUTOMATION" title="Operational automations" description="High-impact actions stay approval-gated." />
      <Notice title="Safety" tone="warning">
        Automations cannot issue refunds, change subscriptions, delete clinical records, or disable
        security controls through this engine.
      </Notice>
      {problem ? <FormError problem={problem} /> : null}
      <Section title="Rules">
        <ul className="dashboard-list">
          {rows.map((row) => (
            <li key={row.rule_id}>
              <div className="list-row">
                <div>
                  <strong>{row.rule_code}</strong>
                  <p className="muted">
                    {row.trigger_type} → {row.action_type}
                  </p>
                </div>
                <div className="row-actions">
                  <StatusBadge status={row.enabled ? "enabled" : "disabled"} />
                  {row.approval_required ? <StatusBadge status="approval-required" /> : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
