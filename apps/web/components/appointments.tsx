"use client";

import type { ReactNode } from "react";
import type { Schemas } from "@/lib/api";
import { formatDayHeading, formatTime, groupByDay, shortId, timeZoneLabel } from "@/lib/time";
import { StatusBadge } from "@/components/ui";

type Appointment = Schemas["AppointmentRead"];

export function AppointmentItem({
  appointment,
  showPatient = false,
  showDate = false,
  actions,
}: {
  appointment: Appointment;
  showPatient?: boolean;
  showDate?: boolean;
  actions?: ReactNode;
}) {
  const zone = appointment.timezone;
  return (
    <li className="appointment-item">
      <div className="appointment-time">
        <strong>{formatTime(appointment.starts_at, zone)}</strong>
        <span>{formatTime(appointment.ends_at, zone)}</span>
      </div>
      <div className="appointment-body">
        {showDate && <p className="appointment-date">{formatDayHeading(appointment.starts_at, zone)}</p>}
        <p className="appointment-title">{appointment.provider_name || "Clinic provider"}</p>
        <p className="appointment-meta">
          {appointment.location_name} · {timeZoneLabel(zone, new Date(appointment.starts_at))}
          {showPatient && <> · Patient ref {shortId(appointment.clinic_patient_id)}</>}
        </p>
      </div>
      <div className="appointment-side">
        <StatusBadge status={appointment.status} />
        {actions}
      </div>
    </li>
  );
}

export function AppointmentDays({
  appointments,
  showPatient = false,
}: {
  appointments: Appointment[];
  showPatient?: boolean;
}) {
  const days = groupByDay(appointments, (item) => item.starts_at, (item) => item.timezone);
  return (
    <div className="day-groups">
      {days.map((day) => (
        <section className="day-group" key={day.key} aria-label={day.label}>
          <h3 className="day-heading">{day.label}</h3>
          <ul className="appointment-list">
            {day.items.map((appointment) => (
              <AppointmentItem appointment={appointment} key={appointment.appointment_id} showPatient={showPatient} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
