"use client";

import { useMemo, useState, type FormEvent } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  Section,
  SelectField,
  StatusBadge,
  SubmitButton,
  TextField,
  useToast,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
import { addDays, dayKey, formatTime, groupByDay, timeZoneLabel, zonedToUtc } from "@/lib/time";

const SLOT_MINUTES = 30;

export default function AvailabilityPage() {
  return (
    <RoleGate roles={["provider"]}>
      <Availability />
    </RoleGate>
  );
}

function Availability() {
  const { tenant_id } = useActiveMembership();
  const { features } = usePortal();
  const notify = useToast();
  const scheduling = features?.schedulingEnabled ?? false;

  const locations = useApiQuery(`locations:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/locations", { params: { path: { tenant_id } } })),
  );
  const slots = useApiQuery(scheduling ? `own-availability:${tenant_id}` : null, () => {
    const from = new Date();
    return call(
      api().GET("/api/v1/tenants/{tenant_id}/providers/me/availability", {
        params: { path: { tenant_id }, query: { from: from.toISOString(), to: addDays(from, 28).toISOString() } },
      }),
    );
  });

  const [locationId, setLocationId] = useState("");
  const [date, setDate] = useState(() => dayKey(addDays(new Date(), 1)));
  const [time, setTime] = useState("09:00");
  const [count, setCount] = useState(4);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [failures, setFailures] = useState<string[]>([]);

  const locationList = locations.state.status === "success" ? locations.state.data : [];
  const location = locationList.find((item) => item.location_id === locationId) ?? locationList[0];

  const preview = useMemo(() => {
    if (!location || !date || !time) return [];
    try {
      const first = zonedToUtc(date, time, location.timezone);
      return Array.from({ length: count }, (_, index) => new Date(first.getTime() + index * SLOT_MINUTES * 60000));
    } catch {
      return [];
    }
  }, [location, date, time, count]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!location) return;
    setProblem(null);
    setFailures([]);
    if (preview.some((start) => start.getUTCMinutes() % SLOT_MINUTES !== 0)) {
      setProblem({
        kind: "invalid",
        status: 422,
        code: "SLOT_BOUNDARY",
        message: "Slots must start on the hour or half hour in UTC. This location's time zone needs a different start time.",
        requestId: "",
        fields: { time: "Choose a start time that falls on a UTC half hour." },
      });
      return;
    }
    if (preview[0] && preview[0].getTime() <= Date.now()) {
      setProblem({
        kind: "invalid",
        status: 422,
        code: "AVAILABILITY_IN_PAST",
        message: "Availability must be in the future.",
        requestId: "",
        fields: { date: "Choose a future date and time." },
      });
      return;
    }
    setPending(true);
    let created = 0;
    const failed: string[] = [];
    let blocking: ApiProblem | null = null;
    for (const start of preview) {
      const result = await call(
        api().POST("/api/v1/tenants/{tenant_id}/providers/me/availability", {
          params: { path: { tenant_id } },
          body: { location_id: location.location_id, starts_at: start.toISOString() },
        }),
      );
      if (result.ok) {
        created += 1;
      } else if (result.problem.kind === "conflict") {
        failed.push(`${formatTime(start.toISOString(), location.timezone)} — already in your availability`);
      } else {
        blocking = result.problem;
        break;
      }
    }
    setPending(false);
    setFailures(failed);
    if (blocking) {
      setProblem(
        blocking.code === "PROVIDER_NOT_VERIFIED"
          ? { ...blocking, message: "You can add availability once your profile is active and a credential is verified." }
          : blocking,
      );
    }
    if (created) {
      notify(`Added ${created} ${created === 1 ? "slot" : "slots"}.`);
      slots.reload();
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="AVAILABILITY"
        title="Your availability"
        description="Open 30-minute slots patients can book. Times are entered in the location's own time zone."
      />

      {!scheduling ? (
        <Notice title="Scheduling is turned off" tone="warning">
          Online booking hasn&apos;t been enabled for this environment, so availability can&apos;t be published yet.
        </Notice>
      ) : (
        <>
          <Section title="Add open slots">
            <QueryView state={locations.state} onRetry={locations.reload} rows={2}>
              {(items) =>
                items.length ? (
                  <form className="form-stack app-card" onSubmit={submit}>
                    <FormError problem={problem} />
                    <div className="form-row form-row-4">
                      <SelectField
                        label="Location"
                        required
                        value={location?.location_id ?? ""}
                        onChange={(event) => setLocationId(event.target.value)}
                        hint={location ? timeZoneLabel(location.timezone) : undefined}
                      >
                        {items.map((item) => (
                          <option key={item.location_id} value={item.location_id}>
                            {item.name}
                          </option>
                        ))}
                      </SelectField>
                      <TextField
                        label="Date"
                        type="date"
                        required
                        min={dayKey(new Date())}
                        value={date}
                        onChange={(event) => setDate(event.target.value)}
                        error={problem?.fields.date}
                      />
                      <TextField
                        label="First slot starts"
                        type="time"
                        required
                        step={1800}
                        value={time}
                        onChange={(event) => setTime(event.target.value)}
                        error={problem?.fields.time}
                      />
                      <SelectField
                        label="Number of slots"
                        value={count}
                        onChange={(event) => setCount(Number(event.target.value))}
                      >
                        {[1, 2, 3, 4, 6, 8, 12, 16].map((value) => (
                          <option key={value} value={value}>
                            {value} ({(value * SLOT_MINUTES) / 60} h)
                          </option>
                        ))}
                      </SelectField>
                    </div>
                    {location && preview.length > 0 && (
                      <p className="form-preview">
                        Adds {preview.length} back-to-back {preview.length === 1 ? "slot" : "slots"} from{" "}
                        <strong>{formatTime(preview[0].toISOString(), location.timezone)}</strong> to{" "}
                        <strong>
                          {formatTime(
                            new Date(preview[preview.length - 1].getTime() + SLOT_MINUTES * 60000).toISOString(),
                            location.timezone,
                          )}
                        </strong>{" "}
                        at {location.name}.
                      </p>
                    )}
                    {failures.length > 0 && (
                      <Notice title="Some slots were skipped" tone="warning">
                        {failures.join("; ")}
                      </Notice>
                    )}
                    <div className="form-actions">
                      <SubmitButton pending={pending} pendingLabel="Adding slots…">
                        Add availability
                      </SubmitButton>
                    </div>
                  </form>
                ) : (
                  <EmptyState title="No clinic locations">
                    A clinic administrator needs to add a location before availability can be published.
                  </EmptyState>
                )
              }
            </QueryView>
          </Section>

          <Section title="Next four weeks">
            <QueryView state={slots.state} onRetry={slots.reload} rows={4} loadingLabel="Loading availability">
              {(items) =>
                items.length ? (
                  <div className="day-groups">
                    {groupByDay(items, (slot) => slot.starts_at, (slot) => slot.timezone).map((day) => (
                      <section className="day-group" key={day.key} aria-label={day.label}>
                        <h3 className="day-heading">{day.label}</h3>
                        <ul className="slot-list">
                          {day.items.map((slot) => (
                            <li className={`slot-chip slot-${slot.status}`} key={slot.availability_id}>
                              <span className="slot-chip-text">
                                <strong>{formatTime(slot.starts_at, slot.timezone)}</strong>
                                <span>{slot.location_name}</span>
                              </span>
                              <StatusBadge status={slot.status} />
                              {slot.status === "open" ? (
                                <button
                                  className="button button-small button-light"
                                  type="button"
                                  onClick={async () => {
                                    const result = await call(
                                      api().DELETE(
                                        "/api/v1/tenants/{tenant_id}/providers/me/availability/{availability_id}",
                                        {
                                          params: {
                                            path: { tenant_id, availability_id: slot.availability_id },
                                          },
                                        },
                                      ),
                                    );
                                    if (result.ok) {
                                      notify("Slot withdrawn.");
                                      slots.reload();
                                    } else {
                                      notify(result.problem.message);
                                    }
                                  }}
                                >
                                  Withdraw
                                </button>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No upcoming availability">Add open slots above so patients can book with you.</EmptyState>
                )
              }
            </QueryView>
          </Section>
        </>
      )}
    </>
  );
}
