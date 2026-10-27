"use client";

import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView, StatusBadge, Table } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { formatDate } from "@/lib/time";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatType(contentType: string): string {
  if (contentType === "application/pdf") return "PDF";
  if (contentType.startsWith("image/")) return `Image (${contentType.slice(6).toUpperCase()})`;
  return contentType;
}

export default function RecordsPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { state, reload } = useApiQuery(`documents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/documents", { params: { path: { tenant_id } } })),
  );

  return (
    <>
      <PageHeader
        eyebrow="RECORDS"
        title="Your documents"
        description={`Documents connected to your care at ${tenant_name}.`}
      />

      <Notice title="Viewing and uploading files isn't available yet">
        Secure document storage hasn&apos;t been enabled for this clinic. You can see what&apos;s on file, but files
        can&apos;t be opened or added here yet.
      </Notice>

      <QueryView state={state} onRetry={reload} rows={4} loadingLabel="Loading documents">
        {(documents) =>
          documents.length ? (
            <Table caption="Your documents">
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
                {documents.map((document) => (
                  <tr key={document.document_id}>
                    <td>
                      <strong className="cell-title">{document.original_filename}</strong>
                    </td>
                    <td>{formatType(document.content_type)}</td>
                    <td>{formatSize(document.size_bytes)}</td>
                    <td>{formatDate(document.created_at)}</td>
                    <td>
                      <StatusBadge status={document.lifecycle_state} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No documents yet">Documents your clinic adds to your record will be listed here.</EmptyState>
          )
        }
      </QueryView>
    </>
  );
}
