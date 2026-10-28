"use client";

import { useRef, useState } from "react";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  StatusBadge,
  Table,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
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
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [downloadProblem, setDownloadProblem] = useState<ApiProblem | null>(null);
  const { state, reload } = useApiQuery(`documents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/documents", { params: { path: { tenant_id } } })),
  );

  async function upload(file: File) {
    setUploading(true);
    setProblem(null);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`/api/v1/tenants/${tenant_id}/documents`, {
        method: "POST",
        body,
        headers: { "x-healthomatix-csrf": "1" },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const error = payload?.error;
        setProblem({
          kind: response.status === 503 ? "unavailable" : response.status === 422 ? "invalid" : "unexpected",
          status: response.status,
          code: typeof error?.code === "string" ? error.code : `HTTP_${response.status}`,
          message:
            typeof error?.message === "string"
              ? error.message
              : "The document could not be uploaded.",
          requestId: typeof error?.request_id === "string" ? error.request_id : "",
          fields: {},
        });
        return;
      }
      reload();
    } catch {
      setProblem({
        kind: "unavailable",
        status: 0,
        code: "NETWORK_ERROR",
        message: "The service could not be reached. Try again shortly.",
        requestId: "",
        fields: {},
      });
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function download(documentId: string, filename: string) {
    setDownloadProblem(null);
    try {
      const response = await fetch(
        `/api/v1/tenants/${tenant_id}/documents/${documentId}/content`,
        { headers: { "x-healthomatix-csrf": "1" } },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const error = payload?.error;
        setDownloadProblem({
          kind: response.status === 503 ? "unavailable" : "unexpected",
          status: response.status,
          code: typeof error?.code === "string" ? error.code : `HTTP_${response.status}`,
          message:
            typeof error?.message === "string"
              ? error.message
              : "The document could not be downloaded.",
          requestId: typeof error?.request_id === "string" ? error.request_id : "",
          fields: {},
        });
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadProblem({
        kind: "unavailable",
        status: 0,
        code: "NETWORK_ERROR",
        message: "The service could not be reached. Try again shortly.",
        requestId: "",
        fields: {},
      });
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="RECORDS"
        title="Your documents"
        description={`Documents connected to your care at ${tenant_name}.`}
        actions={
          <>
            <input
              ref={inputRef}
              className="visually-hidden"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,application/pdf,image/png,image/jpeg,image/webp,text/plain"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
            <button
              className="button button-small"
              type="button"
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
            >
              {uploading ? "Uploading…" : "Upload document"}
            </button>
          </>
        }
      />

      <Notice title="Private storage for this clinic">
        Upload PDF, image, or text files up to 10 MB. Files stay tenant-scoped and are never shared across clinics.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}
      {downloadProblem ? <FormError problem={downloadProblem} /> : null}

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
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
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
                    <td>
                      {document.lifecycle_state === "stored" ? (
                        <button
                          className="button button-small button-light"
                          type="button"
                          onClick={() => void download(document.document_id, document.original_filename)}
                        >
                          Download
                        </button>
                      ) : (
                        <span className="muted">Unavailable</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState
              title="No documents yet"
              action={
                <button
                  className="button button-small"
                  type="button"
                  disabled={uploading}
                  onClick={() => inputRef.current?.click()}
                >
                  Upload your first document
                </button>
              }
            >
              Documents you or your clinic add to this record will be listed here.
            </EmptyState>
          )
        }
      </QueryView>
    </>
  );
}
