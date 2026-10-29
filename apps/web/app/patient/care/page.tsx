"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AppointmentItem } from "@/components/appointments";
import { SlotPicker, type Slot } from "@/components/patient/slot-picker";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import { api, call, newIdempotencyKey, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDayHeading, formatTime, timeZoneLabel } from "@/lib/time";

const STEPS = [
  { id: "clinic", label: "Clinic" },
  { id: "provider", label: "Provider" },
  { id: "time", label: "Time" },
  { id: "confirm", label: "Confirm" },
] as const;

export default function BookCarePage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const scheduling = features?.schedulingEnabled ?? false;
  const [selected, setSelected] = useState<Slot | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [booked, setBooked] = useState<Schemas["AppointmentRead"] | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  function choose(slot: Slot | null) {
    setSelected(slot);
    setProblem(null);
    setIdempotencyKey(newIdempotencyKey());
  }

  async function confirm() {
    if (!selected) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/appointments", {
        params: { path: { tenant_id } },
        body: { availability_id: selected.availability_id, idempotency_key: idempotencyKey },
      }),
    );
    setPending(false);
    if (!result.ok) {
      if (result.problem.code === "SLOT_UNAVAILABLE" || result.problem.code === "PROVIDER_NOT_VERIFIED") {
        setProblem({ ...result.problem, message: "Sorry, that time was just taken. Please choose another." });
        setSelected(null);
        setReloadToken((value) => value + 1);
      } else {
        setProblem(result.problem);
      }
      return;
    }
    setBooked(result.data);
  }

  const activeStep = useMemo(() => {
    if (booked) return 4;
    if (selected) return 3;
    return 2;
  }, [booked, selected]);

  if (!scheduling) {
    return (
      <>
        <PageHeader eyebrow="BOOK CARE" title="Book an appointment" />
        <Notice title="Online booking isn't available yet" tone="warning">
          {tenant_name} hasn&apos;t turned on online scheduling. Please contact the clinic directly to book.
        </Notice>
      </>
    );
  }

  if (booked) {
    return (
      <>
        <PageHeader eyebrow="BOOKED" title="You're booked" description={`Your appointment at ${tenant_name} is confirmed.`} />
        <ol className="booking-steps" aria-label="Booking progress">
          {STEPS.map((step, index) => (
            <li key={step.id} className="is-complete">
              <span className="booking-step-index">{index + 1}</span>
              <span>{step.label}</span>
            </li>
          ))}
          <li className="is-active">
            <span className="booking-step-index">✓</span>
            <span>Confirmed</span>
          </li>
        </ol>
        <ul className="appointment-list appointment-feature">
          <AppointmentItem appointment={booked} showDate />
        </ul>
        <Notice title="Booking confirmed">
          Availability was reserved by the server. You can cancel or reschedule from appointments before your visit.
        </Notice>
        <div className="portal-actions">
          <Link className="button button-small" href="/patient/appointments">
            View my appointments
          </Link>
          <button
            className="button button-light button-small"
            type="button"
            onClick={() => {
              setBooked(null);
              choose(null);
              setReloadToken((value) => value + 1);
            }}
          >
            Book another
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="BOOK CARE"
        title="Book an appointment"
        description={`Select clinic → provider → available time → confirm. Times come from ${tenant_name}'s published availability.`}
      />

      <ol className="booking-steps" aria-label="Booking progress">
        {STEPS.map((step, index) => {
          const complete = index < activeStep;
          const current = index === activeStep;
          return (
            <li key={step.id} className={complete ? "is-complete" : current ? "is-active" : undefined}>
              <span className="booking-step-index">{index + 1}</span>
              <span>{step.label}</span>
            </li>
          );
        })}
      </ol>

      <Notice title="Clinic selected">
        Booking for <strong>{tenant_name}</strong>. Switch clinics from the top bar if you belong to more than one.
      </Notice>

      <FormError problem={problem} />
      <div className="booking-layout">
        <Section title="Choose provider and time" description="Open slots are loaded from the server. Filters narrow the list; confirmation re-checks availability.">
          <SlotPicker tenantId={tenant_id} selected={selected} onSelect={choose} reloadToken={reloadToken} />
        </Section>

        <aside className="booking-summary app-card" aria-labelledby="summary-title">
          <h2 id="summary-title" className="card-title">
            Review and confirm
          </h2>
          {selected ? (
            <>
              <dl className="summary-list">
                <div>
                  <dt>Clinic</dt>
                  <dd>{tenant_name}</dd>
                </div>
                <div>
                  <dt>When</dt>
                  <dd>
                    {formatDayHeading(selected.starts_at, selected.timezone)}
                    <br />
                    {formatTime(selected.starts_at, selected.timezone)} – {formatTime(selected.ends_at, selected.timezone)}
                  </dd>
                </div>
                <div>
                  <dt>With</dt>
                  <dd>{selected.provider_name || "Clinic provider"}</dd>
                </div>
                <div>
                  <dt>Where</dt>
                  <dd>
                    {selected.location_name}
                    <span className="cell-sub">{timeZoneLabel(selected.timezone, new Date(selected.starts_at))}</span>
                  </dd>
                </div>
                <div>
                  <dt>Type</dt>
                  <dd>Visit</dd>
                </div>
              </dl>
              <button
                className="button button-full"
                type="button"
                onClick={confirm}
                disabled={pending}
                aria-busy={pending}
              >
                {pending ? "Booking…" : "Confirm booking"}
              </button>
              <p className="muted summary-note">
                This visit is for scheduling only. In an emergency, call your local emergency number.
              </p>
            </>
          ) : (
            <p className="muted">Pick a provider filter and time to review details here.</p>
          )}
        </aside>
      </div>

      {selected && (
        <div className="mobile-confirm-bar" role="region" aria-label="Selected time">
          <div>
            <strong>{formatTime(selected.starts_at, selected.timezone)}</strong>
            <span>
              {formatDayHeading(selected.starts_at, selected.timezone)} · {selected.provider_name || "Clinic provider"}
            </span>
          </div>
          <button className="button button-small" type="button" onClick={confirm} disabled={pending} aria-busy={pending}>
            {pending ? "Booking…" : "Confirm"}
          </button>
        </div>
      )}
    </>
  );
}
