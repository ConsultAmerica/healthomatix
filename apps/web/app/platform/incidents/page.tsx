"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { EmptyState, FormError, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Incident = {
  incident_id: string;
  incident_number: string;
  severity: string;
  status: string;
  affected_service: string;
  impact_summary: string;
  detected_at: string;
};

export default function IncidentsPage() {
  const [rows, setRows] = useState<Incident[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [service, setService] = useState("api");
  const [severity, setSeverity] = useState("SEV-3");
  const [summary, setSummary] = useState("");

  const load = useCallback(async () => {
    setProblem(null);
    const res = await apiJson<Incident[]>("/api/v1/platform/operations/incidents");
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setRows(res.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    const res = await apiJson<Record<string, unknown>>("/api/v1/platform/operations/incidents", {
      method: "POST",
      body: JSON.stringify({
        category: "operations",
        severity,
        affected_service: service,
        impact_summary: summary,
      }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setSummary("");
    await load();
  }

  async function resolve(id: string) {
    const res = await apiJson(`/api/v1/platform/operations/incidents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "resolved", resolution: "Mitigated in staging." }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader eyebrow="INCIDENTS" title="Incident management" description="SEV lifecycle with auditable events." />
      {problem ? <FormError problem={problem} /> : null}

      <Section title="Open incident">
        <form className="stack-form" onSubmit={(e) => void onCreate(e)}>
          <label>
            Severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option>SEV-1</option>
              <option>SEV-2</option>
              <option>SEV-3</option>
              <option>SEV-4</option>
            </select>
          </label>
          <label>
            Service
            <input value={service} onChange={(e) => setService(e.target.value)} required />
          </label>
          <label>
            Impact summary
            <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Create incident
          </button>
        </form>
      </Section>

      <Section title="Queue">
        {rows.length ? (
          <ul className="dashboard-list">
            {rows.map((row) => (
              <li key={row.incident_id}>
                <div className="list-row">
                  <div>
                    <strong>
                      {row.incident_number} · {row.affected_service}
                    </strong>
                    <p className="muted">
                      {row.severity} · {row.detected_at}
                      <br />
                      {row.impact_summary}
                    </p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={row.status} />
                    {row.status !== "resolved" && row.status !== "closed" ? (
                      <button
                        className="button button-small button-light"
                        type="button"
                        onClick={() => void resolve(row.incident_id)}
                      >
                        Resolve
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No incidents" description="Operational incidents will appear here." />
        )}
      </Section>
    </>
  );
}
