"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  Section,
  StatusBadge,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDateTime, isFuture } from "@/lib/time";

type WaitingEntry = {
  entry_id: string;
  appointment_id: string;
  session_id?: string | null;
  status: string;
  checked_in_at?: string | null;
};

export default function PatientWaitingRoomPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const scheduling = features?.schedulingEnabled ?? false;
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [micOk, setMicOk] = useState(false);
  const [camOk, setCamOk] = useState(false);
  const [entryByAppt, setEntryByAppt] = useState<Record<string, WaitingEntry>>({});

  const appointments = useApiQuery(scheduling ? `wait-appts:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/appointments", { params: { path: { tenant_id } } })),
  );

  const upcoming = useMemo(() => {
    if (appointments.state.status !== "success") return [];
    return appointments.state.data
      .filter((item) => item.status === "booked" && isFuture(item.starts_at))
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  }, [appointments.state]);

  async function checkIn(appointmentId: string) {
    setPending(true);
    setProblem(null);
    const result = await apiJson<WaitingEntry>(
      `/api/v1/tenants/${tenant_id}/appointments/${appointmentId}/check-in`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setEntryByAppt((current) => ({ ...current, [appointmentId]: result.data }));
  }

  async function leave(appointmentId: string) {
    setPending(true);
    setProblem(null);
    const result = await apiJson<WaitingEntry>(
      `/api/v1/tenants/${tenant_id}/appointments/${appointmentId}/leave-waiting-room`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setEntryByAppt((current) => ({ ...current, [appointmentId]: result.data }));
  }

  if (!scheduling) {
    return (
      <>
        <PageHeader eyebrow="WAITING ROOM" title="Virtual waiting room" />
        <Notice title="Online visits aren’t enabled" tone="warning">
          Contact {tenant_name} for visit instructions.
        </Notice>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="WAITING ROOM"
        title="Virtual waiting room"
        description={`${tenant_name} · check in for your virtual visit, confirm devices, then wait for admission.`}
      />

      <Notice title="Privacy & emergencies">
        This waiting room does not show other patients. Portal messaging and video are not for emergencies—
        call emergency services if you need urgent care. Recording is disabled by default.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Device readiness">
        <div className="row-actions">
          <button className="button button-small button-light" type="button" onClick={() => setMicOk(true)}>
            {micOk ? "Microphone ready" : "Test microphone"}
          </button>
          <button className="button button-small button-light" type="button" onClick={() => setCamOk(true)}>
            {camOk ? "Camera ready" : "Test camera"}
          </button>
          <StatusBadge status={micOk && camOk ? "ready" : "pending"} />
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Device checks are browser-local in this demo. Live media uses short-lived tokens from the Fake
          video adapter until a BAA-covered provider is configured.
        </p>
      </Section>

      <Section title="Upcoming virtual visits">
        <QueryView state={appointments.state} onRetry={appointments.reload} rows={3} loadingLabel="Loading visits">
          {() =>
            upcoming.length ? (
              <ul className="dashboard-list">
                {upcoming.map((item) => {
                  const entry = entryByAppt[item.appointment_id];
                  return (
                    <li key={item.appointment_id}>
                      <div>
                        <strong>{item.provider_name || "Your provider"}</strong>
                        <span className="muted">
                          {formatDateTime(item.starts_at, item.timezone)} · {item.location_name || tenant_name}
                        </span>
                        {entry ? <StatusBadge status={entry.status} /> : null}
                      </div>
                      <div className="row-actions">
                        {!entry || entry.status === "left" || entry.status === "not_checked_in" ? (
                          <button
                            className="button button-small"
                            type="button"
                            disabled={pending}
                            onClick={() => void checkIn(item.appointment_id)}
                          >
                            Check in
                          </button>
                        ) : null}
                        {entry?.status === "waiting" || entry?.status === "admitted" ? (
                          <button
                            className="button button-small button-light"
                            type="button"
                            disabled={pending}
                            onClick={() => void leave(item.appointment_id)}
                          >
                            Leave waiting room
                          </button>
                        ) : null}
                        {entry?.session_id && (entry.status === "admitted" || entry.status === "waiting") ? (
                          <Link className="button button-small" href={`/patient/visits/${entry.session_id}`}>
                            Open visit
                          </Link>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState
                title="No upcoming appointments"
                action={
                  <Link className="button button-small" href="/patient/care">
                    Book a visit
                  </Link>
                }
              />
            )
          }
        </QueryView>
      </Section>

      <Section title="After your visit">
        <Link className="button button-small button-light" href="/patient/visit-summary">
          View approved visit summaries
        </Link>
      </Section>
    </>
  );
}
