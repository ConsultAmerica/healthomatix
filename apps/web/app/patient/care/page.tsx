"use client";

import Link from "next/link";
import { useState } from "react";
import { AppointmentItem } from "@/components/appointments";
import { SlotPicker, type Slot } from "@/components/patient/slot-picker";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import { api, call, newIdempotencyKey, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDayHeading, formatTime, timeZoneLabel } from "@/lib/time";

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
    // A new choice is a new booking intent; retries of the same choice reuse the key.
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
        <ul className="appointment-list appointment-feature">
          <AppointmentItem appointment={booked} showDate />
        </ul>
        <Notice title="Need to change plans?">
          You can cancel or reschedule from your appointments at any time before your visit.
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
        description={`Choose a 30-minute visit with a verified provider at ${tenant_name}.`}
      />

      <FormError problem={problem} />
      <div className="booking-layout">
        <Section title="1. Choose a time">
          <SlotPicker tenantId={tenant_id} selected={selected} onSelect={choose} reloadToken={reloadToken} />
        </Section>

        <aside className="booking-summary app-card" aria-labelledby="summary-title">
          <h2 id="summary-title" className="card-title">
            2. Review and confirm
          </h2>
          {selected ? (
            <>
              <dl className="summary-list">
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
            <p className="muted">Pick a day and time to see the details here.</p>
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
