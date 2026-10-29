"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import {
  Breadcrumbs,
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  SearchField,
  StatusBadge,
  Table,
  useToast,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
import { apiJson, type DocumentProcessingJob } from "@/lib/fhir";
import { formatDate } from "@/lib/time";

type DocRow = {
  document_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  lifecycle_state: string;
  processing_status?: string | null;
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatType(contentType: string): string {
  if (contentType === "application/pdf") return "PDF";
  if (contentType.startsWith("image/")) return `Image (${contentType.slice(6).toUpperCase()})`;
  if (contentType === "text/plain") return "Text";
  return contentType;
}

export default function RecordsPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const notify = useToast();
  const storageReady = features?.documentStorageConfigured ?? false;
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [downloadProblem, setDownloadProblem] = useState<ApiProblem | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState("application/octet-stream");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [dragActive, setDragActive] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [jobByDoc, setJobByDoc] = useState<Record<string, DocumentProcessingJob>>({});

  const { state, reload } = useApiQuery(`documents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/documents", { params: { path: { tenant_id } } })),
  );

  const documents: DocRow[] =
    state.status === "success" ? (state.data as DocRow[]) : [];
  const selected = documents.find((doc) => doc.document_id === selectedId) ?? null;

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return documents.filter((doc) => {
      const matchesQuery =
        !needle ||
        doc.original_filename.toLowerCase().includes(needle) ||
        doc.content_type.toLowerCase().includes(needle);
      const matchesType =
        typeFilter === "all" ||
        (typeFilter === "pdf" && doc.content_type === "application/pdf") ||
        (typeFilter === "image" && doc.content_type.startsWith("image/")) ||
        (typeFilter === "text" && doc.content_type.startsWith("text/"));
      return matchesQuery && matchesType;
    });
  }, [documents, query, typeFilter]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    if (!selectedId || !storageReady) {
      setPreviewUrl(null);
      return;
    }
    void (async () => {
      try {
        const response = await fetch(
          `/api/v1/tenants/${tenant_id}/documents/${selectedId}/content`,
          { headers: { "x-healthomatix-csrf": "1" } },
        );
        if (!response.ok || cancelled) return;
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setPreviewUrl(objectUrl);
          setPreviewType(blob.type || "application/octet-stream");
        }
      } catch {
        if (!cancelled) setPreviewUrl(null);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedId, tenant_id, storageReady]);

  async function upload(file: File) {
    setUploading(true);
    setProblem(null);
    setUploadProgress(`Uploading ${file.name}…`);
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
        setUploadProgress(null);
        return;
      }
      const created = (await response.json()) as { document_id?: string };
      setUploadProgress(null);
      notify("Document uploaded successfully.");
      reload();
      if (created.document_id) setSelectedId(created.document_id);
    } catch {
      setUploadProgress(null);
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

  async function processDocument(documentId: string) {
    setProcessingId(documentId);
    setProblem(null);
    const result = await apiJson<DocumentProcessingJob>(
      `/api/v1/tenants/${tenant_id}/documents/${documentId}/process`,
      { method: "POST", body: "{}" },
    );
    setProcessingId(null);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setJobByDoc((current) => ({ ...current, [documentId]: result.data }));
    notify(
      result.data.status === "awaiting_review"
        ? "Processing complete — awaiting clinic review for laboratory rows."
        : `Processing status: ${result.data.status}`,
    );
  }

  async function remove(documentId: string) {
    setProblem(null);
    const result = await call(
      api().DELETE("/api/v1/tenants/{tenant_id}/documents/{document_id}", {
        params: { path: { tenant_id, document_id: documentId } },
      }),
    );
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    if (selectedId === documentId) setSelectedId(null);
    notify("Document removed.");
    reload();
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
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/patient" },
          { label: "Medical Records" },
        ]}
      />
      <PageHeader
        eyebrow="RECORDS"
        title="Medical records"
        description={`Documents connected to your care at ${tenant_name}. Upload files securely; clinic review happens separately.`}
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
            <Link className="button button-small button-light" href="/patient/timeline">
              Health Timeline
            </Link>
            <button
              className="button button-small"
              type="button"
              disabled={uploading || !storageReady}
              onClick={() => inputRef.current?.click()}
              aria-describedby="upload-help"
            >
              {uploading ? "Uploading…" : "Upload document"}
            </button>
          </>
        }
      />

      <p id="upload-help" className="visually-hidden">
        Accepted formats: PDF, PNG, JPEG, WebP, or plain text up to 10 MB.
      </p>

      {storageReady ? (
        <Notice title="Secure document storage">
          Upload PDF, image, or text files up to 10 MB. Verified clinical values appear on your{" "}
          <Link href="/patient/timeline">Health Timeline</Link> only after clinic review—not from
          upload alone.
        </Notice>
      ) : (
        <Notice title="Secure document storage is not configured" tone="warning">
          Listing still works, but uploads and downloads stay unavailable until private storage is enabled.
        </Notice>
      )}

      {uploadProgress ? (
        <Notice title="Upload in progress" tone="info">
          <span role="status" aria-live="polite">
            {uploadProgress}
          </span>
        </Notice>
      ) : null}

      {problem ? <FormError problem={problem} /> : null}
      {downloadProblem ? <FormError problem={downloadProblem} /> : null}

      {storageReady ? (
        <div
          className={`upload-dropzone${dragActive ? " is-active" : ""}${uploading ? " is-busy" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setDragActive(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setDragActive(false);
            const file = event.dataTransfer.files?.[0];
            if (file && !uploading) void upload(file);
          }}
        >
          <strong>Drag and drop a document here</strong>
          <span className="muted">PDF, PNG, JPEG, WebP, or plain text up to 10 MB</span>
          <button
            className="button button-small button-light"
            type="button"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            Or choose a file
          </button>
        </div>
      ) : null}

      <div className="records-toolbar">
        <SearchField
          label="Search medical records"
          value={query}
          onChange={setQuery}
          placeholder="Search by file name…"
        />
        <div className="field records-filter">
          <label htmlFor="records-type-filter">File type</label>
          <select
            id="records-type-filter"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            <option value="all">All types</option>
            <option value="pdf">PDF</option>
            <option value="image">Images</option>
            <option value="text">Text</option>
          </select>
        </div>
      </div>

      <div className={`records-workspace${selected ? " has-drawer" : ""}`}>
        <div className="records-main">
          <QueryView state={state} onRetry={reload} rows={4} loadingLabel="Loading documents">
            {() =>
              filtered.length ? (
                <Table caption="Your medical records">
                  <thead>
                    <tr>
                      <th scope="col">Name</th>
                      <th scope="col">Type</th>
                      <th scope="col">Size</th>
                      <th scope="col">Uploaded</th>
                      <th scope="col">Status</th>
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((document) => (
                      <tr
                        key={document.document_id}
                        className={selectedId === document.document_id ? "is-selected-row" : undefined}
                      >
                        <td>
                          <button
                            type="button"
                            className="text-button cell-title"
                            onClick={() => setSelectedId(document.document_id)}
                          >
                            {document.original_filename}
                          </button>
                        </td>
                        <td>{formatType(document.content_type)}</td>
                        <td>{formatSize(document.size_bytes)}</td>
                        <td>{formatDate(document.created_at)}</td>
                        <td>
                          <StatusBadge
                            status={
                              jobByDoc[document.document_id]?.status ||
                              document.processing_status ||
                              document.lifecycle_state
                            }
                          />
                        </td>
                        <td className="row-actions">
                          <button
                            className="button button-small button-light"
                            type="button"
                            onClick={() => setSelectedId(document.document_id)}
                          >
                            Details
                          </button>
                          {document.lifecycle_state === "stored" && storageReady ? (
                            <button
                              className="button button-small button-light"
                              type="button"
                              disabled={processingId === document.document_id}
                              onClick={() => void processDocument(document.document_id)}
                            >
                              {processingId === document.document_id ? "Processing…" : "Process"}
                            </button>
                          ) : null}
                          {document.lifecycle_state === "stored" && storageReady ? (
                            <button
                              className="button button-small button-light"
                              type="button"
                              onClick={() => void download(document.document_id, document.original_filename)}
                            >
                              Download
                            </button>
                          ) : null}
                          <button
                            className="button button-small button-light"
                            type="button"
                            onClick={() => void remove(document.document_id)}
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : documents.length ? (
                <EmptyState title="No matching documents">
                  Try a different search or clear the file-type filter.
                </EmptyState>
              ) : (
                <EmptyState
                  title="No documents yet"
                  action={
                    <button
                      className="button button-small"
                      type="button"
                      disabled={uploading || !storageReady}
                      onClick={() => inputRef.current?.click()}
                    >
                      Upload your first document
                    </button>
                  }
                >
                  Lab reports and visit summaries you add to this record appear here.
                </EmptyState>
              )
            }
          </QueryView>

          <Notice title="Document intelligence (V1.3)" tone="info">
            Use <strong>Process</strong> to classify and extract laboratory rows asynchronously into a
            clinic review queue. Unverified extractions never appear on your verified Health Timeline or
            trends. Synthetic demos only—AI output is not clinician-approved advice.
          </Notice>
        </div>

        {selected ? (
          <aside className="record-drawer" aria-label="Record details">
            <header className="record-drawer-head">
              <div>
                <p className="section-kicker">Record details</p>
                <h2>{selected.original_filename}</h2>
                <p className="muted">
                  {formatType(selected.content_type)} · {formatSize(selected.size_bytes)} ·{" "}
                  {formatDate(selected.created_at)}
                </p>
              </div>
              <button type="button" className="button button-small button-light" onClick={() => setSelectedId(null)}>
                Close
              </button>
            </header>

            <div className="record-drawer-preview">
              <p className="record-drawer-label">Document preview</p>
              {previewUrl ? (
                previewType.startsWith("image/") ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={previewUrl} alt={`Preview of ${selected.original_filename}`} />
                ) : (
                  <iframe title="Document preview" src={previewUrl} />
                )
              ) : (
                <p className="muted">Preview unavailable. Download the file to review the source.</p>
              )}
            </div>

            <div className="row-actions">
              {selected.lifecycle_state === "stored" && storageReady ? (
                <button
                  className="button button-small button-light"
                  type="button"
                  onClick={() => void download(selected.document_id, selected.original_filename)}
                >
                  Download
                </button>
              ) : null}
              <StatusBadge status={selected.lifecycle_state} />
            </div>
          </aside>
        ) : null}
      </div>
    </>
  );
}
