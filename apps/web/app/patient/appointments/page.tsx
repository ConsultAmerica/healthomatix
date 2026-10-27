"use client";

import Link from "next/link";
import { useState } from "react";
import { AppointmentItem } from "@/components/appointments";
import { SlotPicker, type Slot } from "@/components/patient/slot-picker";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { Dialog, EmptyState, FormError, Notice, PageHeader, QueryView, Section, useToast } from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDateTime, isFuture } from "@/lib/time";

type Appointment = Schemas["AppointmentRead"];

export default function AppointmentsPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const notify = useToast();
  const scheduling = features?.schedulingEnabled ?? false;
  const path = { params: { path: { tenant_id } } };

  const { state, reload } = useApiQuery(scheduling ? `my-appointments:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/appointments", path)),
  );

  const [cancelling, setCancelling] = useState<Appointment | null>(null);
  const [moving, setMoving] = useState<Appointment | null>(null);
  const [newSlot, setNewSlot] = useState<Slot | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [slotReload, setSlotReload] = useState(0);

  async function cancel() {
    if (!cancelling) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/cancel", {
        params: { path: { tenant_id, appointment_id: cancelling.appointment_id } },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setCancelling(null);
    notify("Appointment cancelled.");
    reload();
  }

  async function reschedule() {
    if (!moving || !newSlot) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/appointments/{appointment_id}/reschedule", {
        params: { path: { tenant_id, appointment_id: moving.appointment_id } },
        body: { availability_id: newSlot.availability_id },
      }),
    );
    setPending(false);
    if (!result.ok) {
      if (result.problem.code === "SLOT_UNAVAILABLE") {
        setProblem({ ...result.problem, message: "That time was just taken. Please choose another." });
        setNewSlot(null);
        setSlotReload((value) => value + 1);
      } else {
        setProblem(result.problem);
      }
      return;
    }
    setMoving(null);
    setNewSlot(null);
    notify(`Moved to ${formatDateTime(result.data.starts_at, result.data.timezone)}.`);
    reload();
  }

  if (!scheduling) {
    return (
      <>
        <PageHeader eyebrow="APPOINTMENTS" title="Your appointments" />
        <Notice title="Online scheduling isn't available yet" tone="warning">
          {tenant_name} hasn&apos;t turned on online scheduling. Contact the clinic for appointment details.
        </Notice>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="APPOINTMENTS"
        title="Your appointments"
        description={`Visits you've booked with ${tenant_name}.`}
        actions={
          <Link className="button button-small" href="/patient/care">
            Book an appointment
          </Link>
        }
      />

      <QueryView state={state} onRetry={reload} rows={3} loadingLabel="Loading appointments">
        {(appointments) => {
          const upcoming = appointments
            .filter((item) => item.status === "booked" && isFuture(item.starts_at))
            .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
          const history = appointments
            .filter((item) => !upcoming.includes(item))
            .sort((a, b) => b.starts_at.localeCompare(a.starts_at));
          return (
            <>
              <Section title="Upcoming">
                {upcoming.length ? (
                  <ul className="appointment-list">
                    {upcoming.map((appointment) => (
                      <AppointmentItem
                        key={appointment.appointment_id}
                        appointment={appointment}
                        showDate
                        actions={
                          <div className="item-actions">
                            <button
                              className="button button-light button-small"
                              type="button"
                              onClick={() => {
                                setProblem(null);
                                setNewSlot(null);
                                setMoving(appointment);
                              }}
                            >
                              Reschedule
                            </button>
                            <button
                              className="button button-ghost-danger button-small"
                              type="button"
                              onClick={() => {
                                setProblem(null);
                                setCancelling(appointment);
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        }
                      />
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    title="No upcoming appointments"
                    action={
                      <Link className="button button-small" href="/patient/care">
                        Find a time
                      </Link>
                    }
                  />
                )}
              </Section>
              {history.length > 0 && (
                <Section title="Past and cancelled">
                  <ul className="appointment-list appointment-list-muted">
                    {history.map((appointment) => (
                      <AppointmentItem key={appointment.appointment_id} appointment={appointment} showDate />
                    ))}
                  </ul>
                </Section>
              )}
            </>
          );
        }}
      </QueryView>

      <Dialog
        open={cancelling !== null}
        onClose={() => setCancelling(null)}
        title="Cancel this appointment?"
        description={
          cancelling
            ? `${formatDateTime(cancelling.starts_at, cancelling.timezone)} with ${cancelling.provider_name || "your provider"}. The time will be released for other patients.`
            : undefined
        }
      >
        <div className="form-stack">
          <FormError problem={problem} />
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setCancelling(null)}>
              Keep appointment
            </button>
            <button className="button button-danger button-small" type="button" onClick={cancel} disabled={pending} aria-busy={pending}>
              {pending ? "Cancelling…" : "Cancel appointment"}
            </button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={moving !== null}
        onClose={() => setMoving(null)}
        title="Choose a new time"
        description={
          moving ? `Currently ${formatDateTime(moving.starts_at, moving.timezone)}. Your current time is kept until you confirm.` : undefined
        }
      >
        <div className="form-stack">
          <FormError problem={problem} />
          {moving && (
            <SlotPicker
              tenantId={tenant_id}
              selected={newSlot}
              onSelect={setNewSlot}
              reloadToken={slotReload}
            />
          )}
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setMoving(null)}>
              Keep current time
            </button>
            <button
              className="button button-small"
              type="button"
              onClick={reschedule}
              disabled={!newSlot || pending}
              aria-busy={pending}
            >
              {pending ? "Moving…" : newSlot ? `Move to ${formatDateTime(newSlot.starts_at, newSlot.timezone)}` : "Select a time"}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
