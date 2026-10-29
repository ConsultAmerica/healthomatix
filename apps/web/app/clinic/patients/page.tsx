"use client";

import Link from "next/link";
import { useState } from "react";
import { InviteDialog } from "@/components/clinic/invite-dialog";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, PageHeader, QueryView, StatusBadge, Table } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { formatDate, shortId } from "@/lib/time";

export default function PatientsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <Patients />
    </RoleGate>
  );
}

function Patients() {
  const { tenant_id } = useActiveMembership();
  const [query, setQuery] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const { state, reload } = useApiQuery(`patients:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients", { params: { path: { tenant_id } } })),
  );

  return (
    <>
      <PageHeader
        eyebrow="PATIENTS"
        title="Patient roster"
        description="Patients connected to this clinic. Names and chart details are only shown where a care relationship authorizes it."
        actions={
          <button className="button button-small" type="button" onClick={() => setInviteOpen(true)}>
            Invite a patient
          </button>
        }
      />

      <QueryView state={state} onRetry={reload} rows={5} loadingLabel="Loading patients">
        {(patients) => {
          if (!patients.length) {
            return (
              <EmptyState
                title="No patients yet"
                action={
                  <button className="button button-small" type="button" onClick={() => setInviteOpen(true)}>
                    Invite your first patient
                  </button>
                }
              >
                Patients join with a single-use invitation code from your clinic.
              </EmptyState>
            );
          }
          const needle = query.trim().toLowerCase();
          const filtered = needle
            ? patients.filter(
                (patient) =>
                  (patient.chart_number ?? "").toLowerCase().includes(needle) ||
                  shortId(patient.clinic_patient_id).toLowerCase().includes(needle),
              )
            : patients;
          return (
            <>
              <div className="toolbar">
                <label className="search-field">
                  <span className="visually-hidden">Search patients</span>
                  <input
                    type="search"
                    placeholder="Search by chart number or reference"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <p className="toolbar-label">
                  {filtered.length} of {patients.length}
                </p>
              </div>
              {filtered.length ? (
                <Table caption="Clinic patients">
                  <thead>
                    <tr>
                      <th scope="col">Reference</th>
                      <th scope="col">Chart number</th>
                      <th scope="col">Status</th>
                      <th scope="col">Joined</th>
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((patient) => (
                      <tr key={patient.clinic_patient_id}>
                        <td className="mono">
                          <Link href={`/clinic/patients/${patient.clinic_patient_id}`}>
                            {shortId(patient.clinic_patient_id)}
                          </Link>
                        </td>
                        <td>{patient.chart_number || <span className="muted">Not assigned</span>}</td>
                        <td>
                          <StatusBadge status={patient.status} />
                        </td>
                        <td>{formatDate(patient.created_at)}</td>
                        <td>
                          <Link
                            className="button button-small button-light"
                            href={`/clinic/patients/${patient.clinic_patient_id}`}
                          >
                            Open
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : (
                <EmptyState title="No matches">Try a different chart number or reference.</EmptyState>
              )}
            </>
          );
        }}
      </QueryView>

      <InviteDialog open={inviteOpen} onClose={() => setInviteOpen(false)} defaultRole="patient" />
    </>
  );
}
