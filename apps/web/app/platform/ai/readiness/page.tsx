"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Readiness = Record<string, string | number>;
type CapReadiness = { total: number; by_status: Record<string, number> };
type SecReadiness = {
  open_safety_events: number;
  denied_clinical_context_accesses: number;
  prompt_injection_filter: string;
  forbidden_autonomous_tools: string;
  note: string;
};

export default function AiReadinessPage() {
  const [overview, setOverview] = useState<Readiness | null>(null);
  const [caps, setCaps] = useState<CapReadiness | null>(null);
  const [security, setSecurity] = useState<SecReadiness | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const [o, c, s] = await Promise.all([
      apiJson<Readiness>("/api/v1/platform/ai/readiness"),
      apiJson<CapReadiness>("/api/v1/platform/ai/readiness/capabilities"),
      apiJson<SecReadiness>("/api/v1/platform/ai/readiness/security"),
    ]);
    if (!o.ok) {
      setProblem(o.problem);
      return;
    }
    if (!c.ok) {
      setProblem(c.problem);
      return;
    }
    if (!s.ok) {
      setProblem(s.problem);
      return;
    }
    setOverview(o.data);
    setCaps(c.data);
    setSecurity(s.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="V2.1.1"
        title="AI architecture readiness"
        description="Verified component status from durable tables — not fabricated scores."
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />
      <Notice title="Foundation increment" tone="info">
        V2.1.1 extends the V2.0 orchestrator, tool gateway, and approval engine. No autonomous diagnosis,
        prescribing, or note signing.
      </Notice>
      <p>
        <Link href="/platform/ai">← AI command center</Link>
        {" · "}
        <Link href="/platform/ai/capabilities">Capability registry</Link>
      </p>
      {problem ? <FormError problem={problem} /> : null}
      {overview ? (
        <Section title="Component readiness">
          <div className="stat-grid workboard-stats">
            {Object.entries(overview)
              .filter(([k]) => k !== "note")
              .map(([key, value]) => (
                <div className="stat-tile" key={key}>
                  <span className="stat-label">{key.replaceAll("_", " ")}</span>
                  <strong className="stat-value">{String(value)}</strong>
                </div>
              ))}
          </div>
          <p className="muted">{String(overview.note || "")}</p>
        </Section>
      ) : null}
      {caps ? (
        <Section title="Capability lifecycle counts">
          <pre className="code-block">{JSON.stringify(caps, null, 2)}</pre>
        </Section>
      ) : null}
      {security ? (
        <Section title="Governance readiness">
          <pre className="code-block">{JSON.stringify(security, null, 2)}</pre>
        </Section>
      ) : null}
    </>
  );
}
