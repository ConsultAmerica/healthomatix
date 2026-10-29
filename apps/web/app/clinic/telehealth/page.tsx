"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  Section,
  StatusBadge,
} from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime } from "@/lib/time";

type WaitingEntry = {
  entry_id: string;
  appointment_id: string;
  session_id?: string | null;
  clinic_patient_id: string;
  provider_user_id: string;
  status: string;
  checked_in_at?: string | null;
  admitted_at?: string | null;
};

export default function TelehealthOpsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <TelehealthOps />
    </RoleGate>
  );
}

function TelehealthOps() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [queue, setQueue] = useState<WaitingEntry[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setProblem(null);
    const result = await apiJson<WaitingEntry[]>(`/api/v1/tenants/${tenant_id}/waiting-room`);
    setLoading(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setQueue(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => {
    const waiting = queue.filter((row) => row.status === "waiting" || row.status === "checked_in").length;
    const admitted = queue.filter((row) => row.status === "admitted").length;
    return { waiting, admitted, total: queue.length };
  }, [queue]);

  return (
    <>
      <PageHeader
        eyebrow="TELEHEALTH OPS"
        title="Virtual visit operations"
        description={`${tenant_name} · authorized waiting room and active virtual visit overview.`}
        actions={
          <div className="row-actions">
            <button className="button button-small button-light" type="button" onClick={() => void load()}>
              Refresh
            </button>
            <Link className="button button-small" href="/clinic/consultations">
              Consultation workspace
            </Link>
          </div>
        }
      />

      <Notice title="Operational scope">
        Counts reflect server-authoritative waiting-room state for your membership. Analytics below are
        live queue metrics only—not fabricated historical production reports. Recording remains off.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <div className="stat-grid workboard-stats">
        <div className="stat-tile">
          <span className="stat-label">In queue</span>
          <strong className="stat-value">{counts.total}</strong>
        </div>
        <div className={`stat-tile${counts.waiting ? " stat-attention" : ""}`}>
          <span className="stat-label">Waiting</span>
          <strong className="stat-value">{counts.waiting}</strong>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Admitted</span>
          <strong className="stat-value">{counts.admitted}</strong>
        </div>
      </div>

      <Section title="Current waiting room">
        {loading ? <p className="muted">Loading…</p> : null}
        {!loading && !queue.length ? (
          <EmptyState title="No active waiting-room entries">
            Patients appear after virtual check-in.
          </EmptyState>
        ) : null}
        <ul className="dashboard-list">
          {queue.map((entry) => (
            <li key={entry.entry_id}>
              <div>
                <strong>Patient chart {entry.clinic_patient_id.slice(0, 8)}…</strong>
                <span className="muted">
                  Provider {entry.provider_user_id.slice(0, 8)}…
                  {entry.checked_in_at ? ` · ${formatDateTime(entry.checked_in_at)}` : ""}
                </span>
                <StatusBadge status={entry.status} />
              </div>
              <div className="row-actions">
                {entry.session_id ? (
                  <Link className="button button-small" href={`/clinic/visits/${entry.session_id}`}>
                    Session
                  </Link>
                ) : null}
                <Link
                  className="button button-small button-light"
                  href={`/clinic/consultations?patient=${entry.clinic_patient_id}&appointment=${entry.appointment_id}`}
                >
                  Workspace
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Provider configuration">
        <p className="muted">
          Demo video provider: <strong>fake</strong>. Production candidates requiring BAA review: Daily,
          LiveKit Cloud, Vonage Video, Amazon Chime SDK. Twilio Programmable Video is excluded.
        </p>
      </Section>
    </>
  );
}
