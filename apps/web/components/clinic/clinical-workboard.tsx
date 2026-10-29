"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, LoadingState, ProblemState, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime } from "@/lib/time";

type Workboard = {
  today_appointments: Array<{
    appointment_id: string;
    clinic_patient_id: string;
    chart_number: string;
    starts_at: string;
    ends_at: string;
    provider_user_id?: string;
    provider_name?: string;
    location_name?: string;
    timezone?: string;
    status?: string;
    appointment_type?: string;
  }>;
  waiting_sessions: Array<{
    session_id: string;
    clinic_patient_id: string;
    status: string;
    appointment_id: string;
  }>;
  pending_extractions: Array<{
    extraction_id: string;
    document_id: string;
    clinic_patient_id: string | null;
    field_count: number;
    created_at: string;
  }>;
  pending_drafts: Array<{
    draft_id: string;
    draft_type: string;
    patient_id: string;
    title: string;
    session_id: string | null;
    created_at: string;
  }>;
  counts: {
    today_appointments: number;
    waiting_sessions: number;
    pending_extractions: number;
    pending_drafts: number;
  };
};

export function ClinicalWorkboard({ tenantId }: { tenantId: string }) {
  const [board, setBoard] = useState<Workboard | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setProblem(null);
    const result = await apiJson<Workboard>(`/api/v1/tenants/${tenantId}/workboard?scope=me`);
    setLoading(false);
    if (!result.ok) {
      setProblem(result.problem);
      setBoard(null);
      return;
    }
    setBoard(result.data);
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !board) return <LoadingState label="Loading clinical workboard" rows={4} />;
  if (problem) return <ProblemState problem={problem} onRetry={load} />;
  if (!board) return null;

  const { counts } = board;

  return (
    <div className="clinical-workboard">
      <div className="stat-grid workboard-stats">
        <div className="stat-tile">
          <span className="stat-label">Today&apos;s appointments</span>
          <strong className="stat-value">{counts.today_appointments}</strong>
        </div>
        <div className={`stat-tile${counts.waiting_sessions ? " stat-attention" : ""}`}>
          <span className="stat-label">Waiting / live visits</span>
          <strong className="stat-value">{counts.waiting_sessions}</strong>
        </div>
        <div className={`stat-tile${counts.pending_extractions ? " stat-attention" : ""}`}>
          <span className="stat-label">Lab extractions to verify</span>
          <strong className="stat-value">{counts.pending_extractions}</strong>
        </div>
        <div className={`stat-tile${counts.pending_drafts ? " stat-attention" : ""}`}>
          <span className="stat-label">AI drafts awaiting approval</span>
          <strong className="stat-value">{counts.pending_drafts}</strong>
        </div>
      </div>

      <div className="workboard-grid">
        <section className="app-card workboard-panel">
          <header>
            <h3>Today&apos;s appointments</h3>
            <Link className="button button-light button-small" href="/clinic/schedule">
              Schedule
            </Link>
          </header>
          {board.today_appointments.length ? (
            <ul className="workboard-list">
              {board.today_appointments.map((item) => (
                <li key={item.appointment_id}>
                  <div>
                    <strong>{item.chart_number || "Patient chart"}</strong>
                    <span>
                      {formatDateTime(item.starts_at, item.timezone)}
                      {item.location_name ? ` · ${item.location_name}` : ""}
                      {item.appointment_type ? ` · ${item.appointment_type}` : ""}
                    </span>
                  </div>
                  <div className="row-actions">
                    {item.status ? <StatusBadge status={item.status} /> : null}
                    <Link
                      className="button button-small button-light"
                      href={`/clinic/patients/${item.clinic_patient_id}`}
                    >
                      Open chart
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No visits scheduled today" />
          )}
        </section>

        <section className="app-card workboard-panel">
          <header>
            <h3>Waiting patients</h3>
          </header>
          {board.waiting_sessions.length ? (
            <ul className="workboard-list">
              {board.waiting_sessions.map((item) => (
                <li key={item.session_id}>
                  <div>
                    <strong>Visit session</strong>
                    <StatusBadge status={item.status} />
                  </div>
                  <Link className="button button-small" href={`/clinic/visits/${item.session_id}`}>
                    Admit / open
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No patients waiting" />
          )}
        </section>

        <section className="app-card workboard-panel">
          <header>
            <h3>New lab results</h3>
            <Link className="button button-light button-small" href="/clinic/patients">
              Patients
            </Link>
          </header>
          {board.pending_extractions.length ? (
            <ul className="workboard-list">
              {board.pending_extractions.map((item) => (
                <li key={item.extraction_id}>
                  <div>
                    <strong>{item.field_count} extracted fields</strong>
                    <span>{formatDateTime(item.created_at)}</span>
                  </div>
                  {item.clinic_patient_id ? (
                    <Link
                      className="button button-small"
                      href={`/clinic/patients/${item.clinic_patient_id}/verify/${item.extraction_id}`}
                    >
                      Verify
                    </Link>
                  ) : (
                    <StatusBadge status="pending">Needs chart link</StatusBadge>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No extractions waiting" />
          )}
        </section>

        <section className="app-card workboard-panel">
          <header>
            <h3>Pending notes &amp; tasks</h3>
          </header>
          {board.pending_drafts.length ? (
            <ul className="workboard-list">
              {board.pending_drafts.map((item) => (
                <li key={item.draft_id}>
                  <div>
                    <strong>{item.title || item.draft_type}</strong>
                    <span>
                      {item.draft_type} · {formatDateTime(item.created_at)}
                    </span>
                  </div>
                  {item.session_id ? (
                    <Link className="button button-small button-light" href={`/clinic/visits/${item.session_id}`}>
                      Review in visit
                    </Link>
                  ) : (
                    <StatusBadge status="draft">AI draft</StatusBadge>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No AI drafts pending approval" />
          )}
        </section>
      </div>

      <div className="action-grid workboard-actions">
        <Link className="action-card" href="/clinic/schedule">
          <strong>Start from schedule</strong>
          <span>Open today&apos;s bookings and launch a consultation.</span>
        </Link>
        <Link className="action-card" href="/clinic/patients">
          <strong>Open patient chart</strong>
          <span>Review timeline, labs, and documents with consent.</span>
        </Link>
        <Link className="action-card" href="/clinic/messages">
          <strong>Patient messages</strong>
          <span>Respond to open threads assigned to the clinic.</span>
        </Link>
      </div>
    </div>
  );
}
