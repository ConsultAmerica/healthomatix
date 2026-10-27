"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState, QueryView, SelectField } from "@/components/ui";
import { api, call, useApiQuery, type Schemas } from "@/lib/api";
import { addDays, formatTime, groupByDay, timeZoneLabel } from "@/lib/time";

export type Slot = Schemas["AvailabilityRead"];

/** Lets a patient choose an open slot from verified providers at their clinic. */
export function SlotPicker({
  tenantId,
  selected,
  onSelect,
  excludeId,
  reloadToken = 0,
}: {
  tenantId: string;
  selected: Slot | null;
  onSelect: (slot: Slot | null) => void;
  excludeId?: string;
  reloadToken?: number;
}) {
  const [provider, setProvider] = useState("");
  const [location, setLocation] = useState("");
  const [day, setDay] = useState<string | null>(null);

  const { state, reload } = useApiQuery(`bookable:${tenantId}:${reloadToken}`, () => {
    const from = new Date();
    return call(
      api().GET("/api/v1/tenants/{tenant_id}/availability", {
        params: { path: { tenant_id: tenantId }, query: { from: from.toISOString(), to: addDays(from, 30).toISOString() } },
      }),
    );
  });

  const slots = useMemo(
    () => (state.status === "success" ? state.data.filter((slot) => slot.availability_id !== excludeId) : []),
    [state, excludeId],
  );
  const providers = useMemo(
    () => [...new Map(slots.map((slot) => [slot.provider_user_id, slot.provider_name || "Clinic provider"])).entries()],
    [slots],
  );
  const locations = useMemo(
    () => [...new Map(slots.map((slot) => [slot.location_id, slot.location_name])).entries()],
    [slots],
  );
  const filtered = slots.filter(
    (slot) => (!provider || slot.provider_user_id === provider) && (!location || slot.location_id === location),
  );
  const days = groupByDay(filtered, (slot) => slot.starts_at, (slot) => slot.timezone);
  const activeDay = days.find((group) => group.key === day) ?? days[0];

  useEffect(() => {
    if (selected && !filtered.some((slot) => slot.availability_id === selected.availability_id)) {
      onSelect(null);
    }
  }, [filtered, selected, onSelect]);

  return (
    <QueryView state={state} onRetry={reload} rows={4} loadingLabel="Finding open times">
      {() =>
        slots.length === 0 ? (
          <EmptyState title="No open times right now">
            Your clinic hasn&apos;t published availability for the next 30 days. Check back soon or contact the clinic.
          </EmptyState>
        ) : (
          <div className="slot-picker">
            <div className="form-row">
              <SelectField label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="">Any provider</option>
                {providers.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </SelectField>
              {locations.length > 1 && (
                <SelectField label="Location" value={location} onChange={(event) => setLocation(event.target.value)}>
                  <option value="">Any location</option>
                  {locations.map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </SelectField>
              )}
            </div>

            {days.length === 0 ? (
              <EmptyState title="No times match these filters">Try another provider or location.</EmptyState>
            ) : (
              <>
                <div className="day-picker" role="radiogroup" aria-label="Day">
                  {days.map((group) => (
                    <button
                      key={group.key}
                      type="button"
                      role="radio"
                      aria-checked={activeDay?.key === group.key}
                      className={`day-pill${activeDay?.key === group.key ? " is-active" : ""}`}
                      onClick={() => setDay(group.key)}
                    >
                      <span>{group.label.split(",")[0]}</span>
                      <strong>{group.label.split(",").slice(1).join(",").trim() || group.label}</strong>
                      <small>
                        {group.items.length} {group.items.length === 1 ? "time" : "times"}
                      </small>
                    </button>
                  ))}
                </div>

                {activeDay && (
                  <fieldset className="time-grid">
                    <legend>
                      Times on {activeDay.label}
                      <span className="muted"> · {timeZoneLabel(activeDay.items[0].timezone)}</span>
                    </legend>
                    {activeDay.items.map((slot) => {
                      const checked = selected?.availability_id === slot.availability_id;
                      return (
                        <label className={`time-option${checked ? " is-selected" : ""}`} key={slot.availability_id}>
                          <input
                            type="radio"
                            name="slot"
                            value={slot.availability_id}
                            checked={checked}
                            onChange={() => onSelect(slot)}
                          />
                          <strong>{formatTime(slot.starts_at, slot.timezone)}</strong>
                          <span>{slot.provider_name || "Clinic provider"}</span>
                          {locations.length > 1 && <span>{slot.location_name}</span>}
                        </label>
                      );
                    })}
                  </fieldset>
                )}
              </>
            )}
          </div>
        )
      }
    </QueryView>
  );
}
