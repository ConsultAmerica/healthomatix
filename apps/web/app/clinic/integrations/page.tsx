"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Connection = {
  connection_id: string;
  connection_name: string;
  integration_type: string;
  external_system: string;
  status: string;
  last_success_at: string | null;
  last_error: string;
};

type Monitoring = {
  connections: number;
  transactions: number;
  processed: number;
  awaiting_review: number;
  failed: number;
  jobs_queued: number;
  identity_reviews: number;
  note: string;
};

type Transaction = {
  transaction_id: string;
  message_type: string;
  external_message_id: string;
  status: string;
  error_summary: string;
  received_at: string;
};

export default function IntegrationsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff"]}>
      <IntegrationsWorkspace />
    </RoleGate>
  );
}

function IntegrationsWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [name, setName] = useState("Sandbox EHR");
  const [system, setSystem] = useState("FakeEHR");
  const [type, setType] = useState("fhir_ehr");
  const [baseUrl, setBaseUrl] = useState("https://sandbox.example/fhir");

  const load = useCallback(async () => {
    setProblem(null);
    const [connRes, monRes, txnRes] = await Promise.all([
      apiJson<Connection[]>(`/api/v1/tenants/${tenant_id}/integrations/connections`),
      apiJson<Monitoring>(`/api/v1/tenants/${tenant_id}/integrations/monitoring`),
      apiJson<Transaction[]>(`/api/v1/tenants/${tenant_id}/integrations/transactions`),
    ]);
    if (!connRes.ok) {
      setProblem(connRes.problem);
      return;
    }
    if (!monRes.ok) {
      setProblem(monRes.problem);
      return;
    }
    if (!txnRes.ok) {
      setProblem(txnRes.problem);
      return;
    }
    setConnections(connRes.data);
    setMonitoring(monRes.data);
    setTransactions(txnRes.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    const res = await apiJson<Connection>(`/api/v1/tenants/${tenant_id}/integrations/connections`, {
      method: "POST",
      body: JSON.stringify({
        connection_name: name.trim(),
        integration_type: type,
        external_system: system.trim(),
        base_url: baseUrl.trim(),
        authorized_scopes: ["system/Patient.read", "system/Observation.read"],
      }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function onTest(connectionId: string) {
    setProblem(null);
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/connections/${connectionId}/test`,
      { method: "POST" },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  async function onRetry(transactionId: string) {
    setProblem(null);
    const res = await apiJson<Record<string, unknown>>(
      `/api/v1/tenants/${tenant_id}/integrations/transactions/${transactionId}/retry`,
      { method: "POST" },
    );
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="INTEROPERABILITY"
        title="Integration hub"
        description={`${tenant_name} · FHIR / HL7 sandbox connections, monitoring, and message explorer.`}
        actions={
          <div className="row-actions">
            <button className="button button-small button-light" type="button" onClick={() => void load()}>
              Refresh
            </button>
            <Link className="button button-small button-light" href="/clinic/integrations/identity">
              Identity
            </Link>
            <Link className="button button-small" href="/clinic/integrations/lab">
              Laboratory
            </Link>
          </div>
        }
      />

      <Notice title="Sandbox interoperability" tone="warning">
        Fake EHR and HL7 adapters only. Parsed external data is not clinically verified. Secrets stay
        server-side as opaque references — never shown in this UI.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      {monitoring ? (
        <div className="stat-grid workboard-stats">
          {(
            [
              ["connections", monitoring.connections],
              ["processed", monitoring.processed],
              ["awaiting review", monitoring.awaiting_review],
              ["failed", monitoring.failed],
              ["identity reviews", monitoring.identity_reviews],
              ["jobs queued", monitoring.jobs_queued],
            ] as const
          ).map(([label, value]) => (
            <div className="stat-tile" key={label}>
              <span className="stat-label">{label}</span>
              <strong className="stat-value">{value}</strong>
            </div>
          ))}
        </div>
      ) : null}

      <Section title="Configure connection">
        <form className="stack-form" onSubmit={(e) => void onCreate(e)}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="fhir_ehr">FHIR EHR</option>
              <option value="hl7_lab">HL7 laboratory</option>
              <option value="file_import">File import</option>
            </select>
          </label>
          <label>
            External system
            <input value={system} onChange={(e) => setSystem(e.target.value)} required />
          </label>
          <label>
            FHIR base URL
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          </label>
          <button className="button" type="submit">
            Save connection
          </button>
        </form>
      </Section>

      <Section title="Connections">
        {connections.length ? (
          <ul className="dashboard-list">
            {connections.map((conn) => (
              <li key={conn.connection_id}>
                <div className="list-row">
                  <div>
                    <strong>{conn.connection_name}</strong>
                    <p className="muted">
                      {conn.integration_type} · {conn.external_system}
                      {conn.last_success_at ? ` · last ok ${conn.last_success_at}` : ""}
                    </p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={conn.status} />
                    <button
                      className="button button-small button-light"
                      type="button"
                      onClick={() => void onTest(conn.connection_id)}
                    >
                      Test
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No connections" description="Add a sandbox EHR or laboratory connection." />
        )}
      </Section>

      <Section title="Message explorer">
        {transactions.length ? (
          <ul className="dashboard-list">
            {transactions.map((txn) => (
              <li key={txn.transaction_id}>
                <div className="list-row">
                  <div>
                    <strong>{txn.message_type}</strong>
                    <p className="muted">
                      {txn.external_message_id} · {txn.received_at}
                      {txn.error_summary ? ` · ${txn.error_summary}` : ""}
                    </p>
                  </div>
                  <div className="row-actions">
                    <StatusBadge status={txn.status} />
                    {txn.status !== "processed" ? (
                      <button
                        className="button button-small button-light"
                        type="button"
                        onClick={() => void onRetry(txn.transaction_id)}
                      >
                        Retry
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No transactions" description="Inbound HL7 or FHIR exchange activity appears here." />
        )}
      </Section>
    </>
  );
}
