"use client";

import { useMemo, useState, type FormEvent } from "react";
import { timeZoneOptions } from "@/components/portal/onboarding";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  Dialog,
  EmptyState,
  FormError,
  PageHeader,
  QueryView,
  SelectField,
  SubmitButton,
  Table,
  TextField,
  useToast,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
import { browserTimeZone, timeZoneLabel } from "@/lib/time";

export default function LocationsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <Locations />
    </RoleGate>
  );
}

function Locations() {
  const { tenant_id, role } = useActiveMembership();
  const notify = useToast();
  const zones = useMemo(timeZoneOptions, []);
  const isAdmin = role === "tenant_admin";
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState(browserTimeZone());
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const { state, reload } = useApiQuery(`locations:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/locations", { params: { path: { tenant_id } } })),
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/locations", { params: { path: { tenant_id } }, body: { name, timezone } }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    notify(`${result.data.name} added.`);
    setOpen(false);
    setName("");
    reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="LOCATIONS"
        title="Clinic locations"
        description="Where care happens. Each location's time zone is used for availability and appointment times."
        actions={
          isAdmin && (
            <button className="button button-small" type="button" onClick={() => setOpen(true)}>
              Add location
            </button>
          )
        }
      />

      <QueryView state={state} onRetry={reload} rows={3} loadingLabel="Loading locations">
        {(items) =>
          items.length ? (
            <Table caption="Clinic locations">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Time zone</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.location_id}>
                    <td>
                      <strong className="cell-title">{item.name}</strong>
                    </td>
                    <td>{timeZoneLabel(item.timezone)}</td>
                    <td>
                      {isAdmin ? (
                        <button
                          className="button button-small button-light"
                          type="button"
                          onClick={async () => {
                            const result = await call(
                              api().POST("/api/v1/tenants/{tenant_id}/locations/{location_id}/deactivate", {
                                params: { path: { tenant_id, location_id: item.location_id } },
                              }),
                            );
                            if (result.ok) {
                              notify(`${item.name} deactivated.`);
                              reload();
                            } else {
                              notify(result.problem.message);
                            }
                          }}
                        >
                          Deactivate
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No active locations">
              {isAdmin ? "Add a location to start publishing availability." : "A clinic administrator can add locations."}
            </EmptyState>
          )
        }
      </QueryView>

      <Dialog open={open} onClose={() => setOpen(false)} title="Add a location">
        <form className="form-stack" onSubmit={submit}>
          <FormError problem={problem} />
          <TextField
            label="Location name"
            required
            minLength={2}
            maxLength={160}
            value={name}
            onChange={(event) => setName(event.target.value)}
            error={problem?.fields.name}
          />
          <SelectField
            label="Time zone"
            required
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            error={problem?.fields.timezone}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone.replaceAll("_", " ")}
              </option>
            ))}
          </SelectField>
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <SubmitButton pending={pending} pendingLabel="Adding…">
              Add location
            </SubmitButton>
          </div>
        </form>
      </Dialog>
    </>
  );
}
