"use client";

import { useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView, useToast } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { addDays, dayKey, formatDate, formatTime, shortId, startOfWeek } from "@/lib/time";
import { useRouter } from "next/navigation";

export default function SchedulePage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <Schedule />
    </RoleGate>
  );
}

function Schedule() {
  const membership = useActiveMembership();
  const { features } = usePortal();
  const notify = useToast();
  const router = useRouter();
  const tenant_id = membership.tenant_id;
  const isProvider = membership.role === "provider";
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const weekEnd = addDays(weekStart, 7);
  const scheduling = features?.schedulingEnabled ?? false;

  async function openVisit(appointmentId: string, existingSessionId?: string | null) {
    if (existingSessionId) {
      router.push(`/clinic/visits/${existingSessionId}`);
      return;
    }
    const created = await apiJson<{ session_id: string }>(
      `/api/v1/tenants/${tenant_id}/sessions`,
      { method: "POST", body: JSON.stringify({ appointment_id: appointmentId }) },
    );
    if (!created.ok) {
      notify(created.problem.message);
      return;
    }
    router.push(`/clinic/visits/${created.data.session_id}`);
  }

  const { state, reload } = useApiQuery(scheduling ? `schedule:${tenant_id}:${weekStart.toISOString()}` : null, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/appointments", {
        params: { path: { tenant_id }, query: { from: weekStart.toISOString(), to: weekEnd.toISOString() } },
      }),
    ),
  );

  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => addDays(weekStart, index)), [weekStart]);
  const today = dayKey(new Date());
  const rangeLabel = `${formatDate(weekStart.toISOString())} – ${formatDate(addDays(weekStart, 6).toISOString())}`;

  return (
    <>
      <PageHeader
        eyebrow="SCHEDULE"
        title={isProvider ? "Your schedule" : "Clinic schedule"}
        description={
          isProvider
            ? "Your booked appointments, shown in each location's time zone."
            : "Booked appointments across all providers, shown in each location's time zone."
        }
      />

      {!scheduling ? (
        <Notice title="Scheduling is turned off" tone="warning">
          Online booking hasn&apos;t been enabled for this environment. Appointments appear here once it is.
        </Notice>
      ) : (
        <>
          <div className="toolbar" role="group" aria-label="Week navigation">
            <button className="button button-light button-small" type="button" onClick={() => setWeekStart(addDays(weekStart, -7))}>
              <span aria-hidden="true">←</span> Previous
            </button>
            <button className="button button-light button-small" type="button" onClick={() => setWeekStart(startOfWeek(new Date()))}>
              This week
            </button>
            <button className="button button-light button-small" type="button" onClick={() => setWeekStart(addDays(weekStart, 7))}>
              Next <span aria-hidden="true">→</span>
            </button>
            <p className="toolbar-label" aria-live="polite">
              {rangeLabel}
            </p>
          </div>

          <QueryView state={state} onRetry={reload} rows={5} loadingLabel="Loading schedule">
            {(appointments) => {
              if (!appointments.length) {
                return (
                  <EmptyState title="No appointments this week">
                    Booked appointments will show here. Use the arrows to look at other weeks.
                  </EmptyState>
                );
              }
              return (
                <>
                  <p className="schedule-summary">
                    {appointments.length} booked {appointments.length === 1 ? "appointment" : "appointments"} this week
                  </p>
                  <div className="week-calendar">
                    {days.map((day) => {
                      const key = dayKey(day);
                      const items = appointments.filter((item) => dayKey(item.starts_at, item.timezone) === key);
                      return (
                        <section
                          className={`calendar-day${key === today ? " is-today" : ""}${items.length ? "" : " is-empty"}`}
                          key={key}
                          aria-label={formatDate(day.toISOString())}
                        >
                          <h3 className="calendar-day-heading">
                            <span>{new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(day)}</span>
                            <strong>{day.getDate()}</strong>
                          </h3>
                          {items.length ? (
                            <ul className="calendar-events">
                              {items.map((appointment) => (
                                <li className="calendar-event" key={appointment.appointment_id}>
                                  <time dateTime={appointment.starts_at}>
                                    {formatTime(appointment.starts_at, appointment.timezone)}–
                                    {formatTime(appointment.ends_at, appointment.timezone)}
                                  </time>
                                  <strong>{appointment.provider_name || "Clinic provider"}</strong>
                                  <span>{appointment.location_name}</span>
                                  {!isProvider && <span className="mono">Patient {shortId(appointment.clinic_patient_id)}</span>}
                                  {appointment.status === "booked" ? (
                                    <div className="row-actions">
                                      <button
                                        className="button button-small"
                                        type="button"
                                        onClick={() =>
                                          void openVisit(
                                            appointment.appointment_id,
                                            (appointment as { session_id?: string | null }).session_id,
                                          )
                                        }
                                      >
                                        Open visit
                                      </button>
                                      <button
                                        className="button button-small button-light"
                                        type="button"
                                        onClick={async () => {
                                          const result = await call(
                                            api().POST("/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/cancel", {
                                              params: {
                                                path: {
                                                  tenant_id,
                                                  appointment_id: appointment.appointment_id,
                                                },
                                              },
                                            }),
                                          );
                                          if (result.ok) {
                                            notify("Appointment cancelled.");
                                            reload();
                                          } else {
                                            notify(result.problem.message);
                                          }
                                        }}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="day-empty">No bookings</p>
                          )}
                        </section>
                      );
                    })}
                  </div>
                </>
              );
            }}
          </QueryView>
        </>
      )}
    </>
  );
}
