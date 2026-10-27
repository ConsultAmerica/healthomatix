"use client";

import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, PageHeader, QueryView, Table } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/time";

export default function AuditPage() {
  return (
    <RoleGate roles={["tenant_admin", "auditor"]}>
      <Audit />
    </RoleGate>
  );
}

function describe(action: string): string {
  const [area, verb = ""] = action.split(".");
  const text = `${area.replaceAll("_", " ")} — ${verb.replaceAll("_", " ")}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Audit() {
  const { tenant_id } = useActiveMembership();
  const [limit, setLimit] = useState(50);
  const [filter, setFilter] = useState("");
  const { state, reload } = useApiQuery(`audit:${tenant_id}:${limit}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/audit-events", { params: { path: { tenant_id }, query: { limit } } })),
  );

  return (
    <>
      <PageHeader
        eyebrow="AUDIT LOG"
        title="Clinic activity"
        description="A tamper-evident record of who did what and when. Events reference records by ID and never include clinical content."
        actions={
          <button className="button button-light button-small" type="button" onClick={reload}>
            Refresh
          </button>
        }
      />

      <div className="toolbar">
        <label className="search-field">
          <span className="visually-hidden">Filter events</span>
          <input
            type="search"
            placeholder="Filter by action, e.g. invitation"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
        </label>
        <label className="inline-select">
          Show
          <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
            {[25, 50, 100].map((value) => (
              <option key={value} value={value}>
                latest {value}
              </option>
            ))}
          </select>
        </label>
      </div>

      <QueryView state={state} onRetry={reload} rows={6} loadingLabel="Loading audit events">
        {(events) => {
          const needle = filter.trim().toLowerCase();
          const visible = needle ? events.filter((event) => event.action.toLowerCase().includes(needle)) : events;
          return visible.length ? (
            <Table caption="Audit events">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Event</th>
                  <th scope="col">Subject</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Request</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((event) => (
                  <tr key={event.event_id}>
                    <td>
                      <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                    </td>
                    <td>{describe(event.action)}</td>
                    <td>
                      {event.subject_type.replaceAll("_", " ")}
                      <span className="cell-sub mono">{event.subject_id ? shortId(event.subject_id) : "—"}</span>
                    </td>
                    <td className="mono">{event.actor_user_id ? shortId(event.actor_user_id) : "System"}</td>
                    <td className="mono">{event.request_id ? event.request_id.slice(0, 8) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title={needle ? "No matching events" : "No activity yet"} />
          );
        }}
      </QueryView>
    </>
  );
}
