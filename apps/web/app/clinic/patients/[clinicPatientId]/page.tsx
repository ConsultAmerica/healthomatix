"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView, StatusBadge, Table } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { formatDate, shortId } from "@/lib/time";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ClinicPatientDetailPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff"]}>
      <ClinicPatientDetail />
    </RoleGate>
  );
}

function ClinicPatientDetail() {
  const params = useParams<{ clinicPatientId: string }>();
  const clinicPatientId = params.clinicPatientId;
  const { tenant_id } = useActiveMembership();

  const detail = useApiQuery(`patient:${tenant_id}:${clinicPatientId}`, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}", {
        params: { path: { tenant_id, clinic_patient_id: clinicPatientId } },
      }),
    ),
  );
  const documents = useApiQuery(`patient-docs:${tenant_id}:${clinicPatientId}`, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents", {
        params: { path: { tenant_id, clinic_patient_id: clinicPatientId } },
      }),
    ),
  );

  return (
    <>
      <PageHeader
        eyebrow="PATIENT"
        title="Clinic patient detail"
        description="Roster-safe summary for this clinic relationship. Chart PHI stays masked without an authorized care relationship."
        actions={
          <Link className="button button-small button-light" href="/clinic/patients">
            Back to roster
          </Link>
        }
      />

      <QueryView state={detail.state} onRetry={detail.reload} rows={3} loadingLabel="Loading patient">
        {(patient) => (
          <>
            <div className="metric-strip">
              <article>
                <strong className="mono">{shortId(patient.clinic_patient_id)}</strong>
                <span>Reference</span>
              </article>
              <article>
                <strong>{patient.chart_number || "Not assigned"}</strong>
                <span>Chart number</span>
              </article>
              <article>
                <StatusBadge status={patient.status} />
                <span>Status</span>
              </article>
              <article>
                <strong>{formatDate(patient.created_at)}</strong>
                <span>Joined</span>
              </article>
            </div>

            <div className="metric-strip">
              <article>
                <strong>{patient.document_count}</strong>
                <span>Documents on file</span>
              </article>
              <article>
                <strong>{patient.open_thread_count}</strong>
                <span>Open message threads</span>
              </article>
              <article>
                <strong>{patient.upcoming_appointment_count}</strong>
                <span>Booked appointments</span>
              </article>
            </div>
          </>
        )}
      </QueryView>

      <Notice title="Privacy boundary">
        This view shows clinic-assigned identifiers and aggregate counts only. Names, contact details, and
        document contents are not exposed here.
      </Notice>

      <QueryView
        state={documents.state}
        onRetry={documents.reload}
        rows={4}
        loadingLabel="Loading document metadata"
      >
        {(rows) =>
          rows.length ? (
            <Table caption="Document metadata">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Type</th>
                  <th scope="col">Size</th>
                  <th scope="col">Added</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((document) => (
                  <tr key={document.document_id}>
                    <td>
                      <strong className="cell-title">{document.original_filename}</strong>
                    </td>
                    <td>{document.content_type}</td>
                    <td>{formatBytes(document.size_bytes)}</td>
                    <td>{formatDate(document.created_at)}</td>
                    <td>
                      <StatusBadge status={document.lifecycle_state} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No documents on file">
              When the patient uploads records, metadata appears here.
            </EmptyState>
          )
        }
      </QueryView>
    </>
  );
}
