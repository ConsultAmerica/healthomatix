"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Ticket = {
  ticket_id: string;
  category: string;
  priority: string;
  status: string;
  subject: string;
  summary: string;
  created_at: string;
};

export default function SupportPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider", "patient"]}>
      <SupportWorkspace />
    </RoleGate>
  );
}

function SupportWorkspace() {
  const { tenant_id, tenant_name, role } = useActiveMembership();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [subject, setSubject] = useState("");
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("technical");

  const canList = role === "tenant_admin" || role === "staff";

  const load = useCallback(async () => {
    if (!canList) return;
    setProblem(null);
    const res = await apiJson<Ticket[]>(`/api/v1/tenants/${tenant_id}/support/tickets`);
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setTickets(res.data);
  }, [tenant_id, canList]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    const res = await apiJson<Ticket>(`/api/v1/tenants/${tenant_id}/support/tickets`, {
      method: "POST",
      body: JSON.stringify({
        category,
        subject: subject.trim(),
        summary: summary.trim(),
        priority: "normal",
      }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setSubject("");
    setSummary("");
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="SUPPORT"
        title="Help desk"
        description={`${tenant_name} · operational support tickets without clinical dumps.`}
      />

      <Notice title="Do not paste clinical details" tone="warning">
        Tickets are for access and product issues. Do not include diagnoses, prescriptions, MRNs, or
        full clinical notes.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Create ticket">
        <form className="stack-form" onSubmit={(e) => void onCreate(e)}>
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="technical">Technical</option>
              <option value="clinic_admin">Clinic admin</option>
              <option value="provider">Provider</option>
              <option value="billing">Billing</option>
              <option value="patient">Patient</option>
              <option value="security">Security</option>
            </select>
          </label>
          <label>
            Subject
            <input value={subject} onChange={(e) => setSubject(e.target.value)} required />
          </label>
          <label>
            Summary
            <textarea rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Submit ticket
          </button>
        </form>
      </Section>

      {canList ? (
        <Section title="Open tickets">
          {tickets.length ? (
            <ul className="dashboard-list">
              {tickets.map((ticket) => (
                <li key={ticket.ticket_id}>
                  <div className="list-row">
                    <div>
                      <strong>{ticket.subject}</strong>
                      <p className="muted">
                        {ticket.category} · {ticket.priority} · {ticket.created_at}
                      </p>
                    </div>
                    <StatusBadge status={ticket.status} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No tickets" description="Clinic support requests will appear here." />
          )}
        </Section>
      ) : null}
    </>
  );
}
