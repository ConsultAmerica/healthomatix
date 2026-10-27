"use client";

import { useMemo, useState } from "react";
import { AppointmentItem } from "@/components/appointments";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { addDays, dayKey, formatDate, startOfWeek } from "@/lib/time";

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
  const tenant_id = membership.tenant_id;
  const isProvider = membership.role === "provider";
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const weekEnd = addDays(weekStart, 7);
  const scheduling = features?.schedulingEnabled ?? false;

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
                <div className="week-grid">
                  {days.map((day) => {
                    const key = dayKey(day);
                    const items = appointments.filter((item) => dayKey(item.starts_at, item.timezone) === key);
                    return (
                      <section
                        className={`week-day${key === today ? " is-today" : ""}`}
                        key={key}
                        aria-label={formatDate(day.toISOString())}
                      >
                        <h3 className="day-heading">
                          {new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" }).format(day)}
                          {key === today && <span className="today-chip">Today</span>}
                        </h3>
                        {items.length ? (
                          <ul className="appointment-list">
                            {items.map((appointment) => (
                              <AppointmentItem
                                appointment={appointment}
                                key={appointment.appointment_id}
                                showPatient={!isProvider}
                              />
                            ))}
                          </ul>
                        ) : (
                          <p className="day-empty">No appointments</p>
                        )}
                      </section>
                    );
                  })}
                </div>
              );
            }}
          </QueryView>
        </>
      )}
    </>
  );
}
