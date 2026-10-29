"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  LoadingState,
  Notice,
  PageHeader,
  ProblemState,
  SearchField,
  Section,
  StatusBadge,
} from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { api, call, useApiQuery } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime, formatTime } from "@/lib/time";

type Workboard = {
  today_appointments: Array<{
    appointment_id: string;
    clinic_patient_id: string;
    chart_number: string;
    starts_at: string;
    ends_at: string;
    provider_user_id: string;
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

export default function DoctorHomePage() {
  return (
    <RoleGate roles={["provider", "tenant_admin", "staff"]}>
      <DoctorHome />
    </RoleGate>
  );
}

function DoctorHome() {
  const { tenant_id, tenant_name, role } = useActiveMembership();
  const isProvider = role === "provider";
  const [board, setBoard] = useState<Workboard | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(true);
  const [queueQuery, setQueueQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [waitingRoom, setWaitingRoom] = useState<
    Array<{
      entry_id: string;
      appointment_id: string;
      session_id?: string | null;
      clinic_patient_id: string;
      status: string;
      checked_in_at?: string | null;
    }>
  >([]);
  const [admitPending, setAdmitPending] = useState(false);

  const threads = useApiQuery(`doctor-threads:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/threads", { params: { path: { tenant_id } } })),
  );

  const load = useCallback(async () => {
    setLoading(true);
    setProblem(null);
    const scope = isProvider ? "me" : "clinic";
    const result = await apiJson<Workboard>(`/api/v1/tenants/${tenant_id}/workboard?scope=${scope}`);
    const waiting = await apiJson<typeof waitingRoom>(`/api/v1/tenants/${tenant_id}/waiting-room`);
    setLoading(false);
    if (!result.ok) {
      setProblem(result.problem);
      setBoard(null);
      return;
    }
    setBoard(result.data);
    if (waiting.ok) setWaitingRoom(waiting.data);
  }, [tenant_id, isProvider]);

  async function admitPatient(appointmentId: string) {
    setAdmitPending(true);
    setProblem(null);
    const result = await apiJson(
      `/api/v1/tenants/${tenant_id}/appointments/${appointmentId}/admit`,
      { method: "POST", body: "{}" },
    );
    setAdmitPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    await load();
  }

  useEffect(() => {
    void load();
  }, [load]);

  const queue = useMemo(() => {
    if (!board) return [];
    const needle = queueQuery.trim().toLowerCase();
    return board.today_appointments.filter((item) => {
      const status = item.status || "booked";
      const matchesStatus = statusFilter === "all" || status === statusFilter;
      const haystack = `${item.chart_number} ${item.provider_name || ""} ${item.location_name || ""}`.toLowerCase();
      const matchesQuery = !needle || haystack.includes(needle);
      return matchesStatus && matchesQuery;
    });
  }, [board, queueQuery, statusFilter]);

  const openMessages =
    threads.state.status === "success"
      ? threads.state.data.filter((thread) => thread.status === "open").slice(0, 5)
      : [];

  const todayLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  return (
    <>
      <PageHeader
        eyebrow="DOCTOR WORKSPACE"
        title={isProvider ? "Today’s schedule" : "Clinical board"}
        description={`${tenant_name} · ${todayLabel}. Schedule, patient queue, and supported pending tasks for your membership.`}
        actions={
          <div className="row-actions">
            <Link className="button button-small button-light" href="/clinic/schedule">
              View schedule
            </Link>
            <Link className="button button-small button-light" href="/clinic/patients">
              Search patients
            </Link>
            <Link className="button button-small button-light" href="/clinic/messages">
              Messages
            </Link>
            {isProvider ? (
              <Link className="button button-small" href="/clinic/availability">
                Manage availability
              </Link>
            ) : null}
          </div>
        }
      />

      {role === "tenant_admin" ? (
        <Notice title="Admin viewing clinical board">
          Clinic administrators manage locations, staff, and credentials from{" "}
          <Link href="/clinic">Clinic overview</Link>. This board uses authorized clinic membership
          scope—not unrestricted chart access.
        </Notice>
      ) : null}

      {loading && !board ? <LoadingState label="Loading doctor workspace" rows={4} /> : null}
      {problem ? <ProblemState problem={problem} onRetry={load} /> : null}

      {board ? (
        <>
          <div className="stat-grid workboard-stats">
            <div className="stat-tile">
              <span className="stat-label">Today&apos;s appointments</span>
              <strong className="stat-value">{board.counts.today_appointments}</strong>
            </div>
            <div className={`stat-tile${board.counts.waiting_sessions ? " stat-attention" : ""}`}>
              <span className="stat-label">Waiting / live visits</span>
              <strong className="stat-value">{board.counts.waiting_sessions}</strong>
            </div>
            <div className={`stat-tile${openMessages.length ? " stat-attention" : ""}`}>
              <span className="stat-label">Open messages</span>
              <strong className="stat-value">{openMessages.length || "0"}</strong>
            </div>
            <div className={`stat-tile${board.counts.pending_extractions ? " stat-attention" : ""}`}>
              <span className="stat-label">Document reviews</span>
              <strong className="stat-value">{board.counts.pending_extractions}</strong>
            </div>
          </div>

          {/* Section A — Today's schedule */}
          <Section title="Today’s schedule" actions={<button className="button button-light button-small" type="button" onClick={() => void load()}>Refresh</button>}>
            {board.today_appointments.length ? (
              <div className="table-scroll" tabIndex={0} role="region" aria-label="Today’s appointments">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">Patient</th>
                      <th scope="col">Type</th>
                      <th scope="col">Location</th>
                      <th scope="col">Status</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {board.today_appointments.map((item) => (
                      <tr key={item.appointment_id}>
                        <td>
                          <strong>{formatTime(item.starts_at, item.timezone)}</strong>
                          <div className="muted">{formatTime(item.ends_at, item.timezone)}</div>
                        </td>
                        <td>{item.chart_number || "Chart pending"}</td>
                        <td>{item.appointment_type || "Visit"}</td>
                        <td>{item.location_name || "—"}</td>
                        <td>
                          <StatusBadge status={item.status || "booked"} />
                        </td>
                        <td>
                          <Link
                            className="button button-small button-light"
                            href={`/clinic/patients/${item.clinic_patient_id}`}
                          >
                            Open chart
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No visits scheduled today">
                New bookings for your authorized schedule appear here.
              </EmptyState>
            )}
          </Section>

          <Section
            title="Virtual waiting room"
            description="Patients who checked in for authorized virtual visits. Admit only applies to your schedule."
            actions={
              <Link className="button button-small button-light" href="/clinic/consultations">
                Consultation workspace
              </Link>
            }
          >
            {waitingRoom.length ? (
              <ul className="dashboard-list">
                {waitingRoom.map((entry) => (
                  <li key={entry.entry_id}>
                    <div>
                      <strong>Chart {entry.clinic_patient_id.slice(0, 8)}…</strong>
                      <span className="muted">
                        {entry.checked_in_at
                          ? `Checked in ${formatDateTime(entry.checked_in_at)}`
                          : "Checked in"}
                      </span>
                      <StatusBadge status={entry.status} />
                    </div>
                    <div className="row-actions">
                      {(entry.status === "waiting" || entry.status === "checked_in") && (
                        <button
                          className="button button-small"
                          type="button"
                          disabled={admitPending}
                          onClick={() => void admitPatient(entry.appointment_id)}
                        >
                          Admit
                        </button>
                      )}
                      {entry.session_id ? (
                        <Link className="button button-small" href={`/clinic/visits/${entry.session_id}`}>
                          Open visit
                        </Link>
                      ) : null}
                      <Link
                        className="button button-small button-light"
                        href={`/clinic/patients/${entry.clinic_patient_id}`}
                      >
                        Chart
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No patients in the waiting room" />
            )}
          </Section>

          {/* Section B — Patient queue */}
          <Section title="Patient queue" description="Today’s patients in appointment order. Search and filters stay within your authorized clinic scope.">
            <div className="records-toolbar">
              <SearchField
                label="Search today’s queue"
                value={queueQuery}
                onChange={setQueueQuery}
                placeholder="Search chart number, provider, location…"
              />
              <div className="field records-filter">
                <label htmlFor="queue-status">Status</label>
                <select
                  id="queue-status"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="all">All</option>
                  <option value="booked">Scheduled / booked</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
            </div>
            {queue.length ? (
              <ul className="dashboard-list" style={{ marginTop: 12 }}>
                {queue.map((item) => (
                  <li key={`queue-${item.appointment_id}`}>
                    <div>
                      <strong>{item.chart_number || "Patient chart"}</strong>
                      <span className="muted">
                        {formatDateTime(item.starts_at, item.timezone)} · {item.location_name || "Clinic"} ·{" "}
                        {item.appointment_type || "Visit"}
                      </span>
                    </div>
                    <div className="row-actions">
                      <StatusBadge status={item.status || "booked"} />
                      <Link
                        className="button button-small"
                        href={`/clinic/patients/${item.clinic_patient_id}`}
                      >
                        Open chart
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No matching patients in today’s queue" />
            )}
          </Section>

          {/* Section C — Pending tasks */}
          <Section title="Pending tasks" description="Outstanding items supported by the backend for this clinic.">
            <div className="workboard-grid">
              <section className="app-card workboard-panel">
                <header>
                  <h3>Waiting visits</h3>
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
                          Open visit
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
                  <h3>Document reviews</h3>
                </header>
                {board.pending_extractions.length ? (
                  <ul className="workboard-list">
                    {board.pending_extractions.map((item) => (
                      <li key={item.extraction_id}>
                        <div>
                          <strong>{item.field_count} extracted fields</strong>
                          <span className="muted">{formatDateTime(item.created_at)}</span>
                        </div>
                        {item.clinic_patient_id ? (
                          <Link
                            className="button button-small button-light"
                            href={`/clinic/patients/${item.clinic_patient_id}/verify/${item.extraction_id}`}
                          >
                            Review
                          </Link>
                        ) : (
                          <span className="muted">Patient link unavailable</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No document reviews waiting" />
                )}
              </section>

              <section className="app-card workboard-panel">
                <header>
                  <h3>Patient messages</h3>
                  <Link className="button button-light button-small" href="/clinic/messages">
                    Inbox
                  </Link>
                </header>
                {openMessages.length ? (
                  <ul className="workboard-list">
                    {openMessages.map((thread) => (
                      <li key={thread.thread_id}>
                        <div>
                          <strong>{thread.subject || "Conversation"}</strong>
                          <span className="muted">{thread.message_count} messages</span>
                        </div>
                        <Link className="button button-small button-light" href="/clinic/messages">
                          Open
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No open patient messages" />
                )}
              </section>
            </div>
            {board.counts.pending_drafts > 0 ? (
              <Notice title="AI drafts are sandbox review items" tone="info">
                {board.counts.pending_drafts} draft item(s) exist for clinician approval in the demo path.
                They are not presented as signed clinical notes.
              </Notice>
            ) : null}
          </Section>

          {/* Section D — Quick actions */}
          <Section title="Quick actions">
            <div className="action-grid">
              <Link className="action-card" href="/clinic/schedule">
                <strong>View schedule</strong>
                <span>Open the clinic appointment board.</span>
              </Link>
              <Link className="action-card" href="/clinic/patients">
                <strong>Search patients</strong>
                <span>Find authorized clinic patient charts.</span>
              </Link>
              <Link className="action-card" href="/clinic/messages">
                <strong>View messages</strong>
                <span>Respond to permitted patient conversations.</span>
              </Link>
              {isProvider ? (
                <Link className="action-card" href="/clinic/availability">
                  <strong>Manage availability</strong>
                  <span>Publish open slots for booking.</span>
                </Link>
              ) : null}
            </div>
          </Section>
        </>
      ) : null}
    </>
  );
}
