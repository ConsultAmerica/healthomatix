"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, StatusBadge, TextField } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson, type Extraction, type ExtractionField } from "@/lib/fhir";

export default function VerifyExtractionPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <VerifyExtraction />
    </RoleGate>
  );
}

function VerifyExtraction() {
  const params = useParams<{ clinicPatientId: string; extractionId: string }>();
  const { tenant_id } = useActiveMembership();
  const router = useRouter();
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [fields, setFields] = useState<ExtractionField[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<string>("text/plain");
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    let objectUrl: string | null = null;
    void (async () => {
      const result = await apiJson<Extraction>(
        `/api/v1/tenants/${tenant_id}/extractions/${params.extractionId}`,
      );
      if (!result.ok) {
        setProblem(result.problem);
        return;
      }
      setExtraction(result.data);
      setFields(result.data.fields);

      try {
        const response = await fetch(
          `/api/v1/tenants/${tenant_id}/documents/${result.data.document_id}/content`,
          { headers: { "x-healthomatix-csrf": "1" } },
        );
        if (response.ok) {
          const blob = await response.blob();
          objectUrl = URL.createObjectURL(blob);
          setPreviewUrl(objectUrl);
          setPreviewType(blob.type || "application/octet-stream");
        }
      } catch {
        // Preview is best-effort; OCR text remains available.
      }
    })();
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [tenant_id, params.extractionId]);

  function updateField(index: number, patch: Partial<ExtractionField>) {
    setFields((prev) => prev.map((field, i) => (i === index ? { ...field, ...patch } : field)));
  }

  const selected = fields[selectedIndex] ?? null;
  const highlightedOcr = useMemo(() => {
    if (!extraction?.ocr_text) return null;
    const needle = selected?.source_text || selected?.name;
    if (!needle) return extraction.ocr_text;
    const idx = extraction.ocr_text.toLowerCase().indexOf(needle.toLowerCase().split("\n")[0] || needle);
    if (idx < 0) return extraction.ocr_text;
    const before = extraction.ocr_text.slice(0, idx);
    const match = extraction.ocr_text.slice(idx, idx + (needle.split("\n")[0] || needle).length);
    const after = extraction.ocr_text.slice(idx + match.length);
    return { before, match, after };
  }, [extraction, selected]);

  async function verify() {
    setPending(true);
    setProblem(null);
    const payloadFields = fields.map((field) => ({
      ...field,
      verification_status:
        field.verification_status === "rejected" ? "rejected" : field.verification_status || "verified",
    }));
    const result = await apiJson<{ extraction: Extraction }>(
      `/api/v1/tenants/${tenant_id}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ extraction_id: params.extractionId, fields: payloadFields }),
      },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    router.push(`/clinic/patients/${params.clinicPatientId}?tab=labs`);
  }

  const locked = extraction?.status === "verified";

  return (
    <>
      <PageHeader
        eyebrow="DOCUMENT INTELLIGENCE"
        title="Laboratory extraction review"
        description="Side-by-side source verification. Corrected values keep original AI extracts. Only authorized clinic roles promote observations."
        actions={
          <Link
            className="button button-small button-light"
            href={`/clinic/patients/${params.clinicPatientId}`}
          >
            Back to patient
          </Link>
        }
      />

      {problem ? <FormError problem={problem} /> : null}

      <Notice title="Clinical verification boundary">
        Patient upload confirmation is not clinician verification. Low-confidence and ambiguous rows stay
        reviewable. Rejected rows are not promoted to verified Observations or health trends.
      </Notice>

      {extraction ? (
        <div className="verify-split">
          <div className="app-card" style={{ padding: 16 }}>
            <h2 className="section-title">Original document</h2>
            {previewUrl && previewType.startsWith("image/") ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={previewUrl} alt="Uploaded document" style={{ maxWidth: "100%" }} />
            ) : previewUrl && previewType === "application/pdf" ? (
              <iframe title="Document preview" src={previewUrl} style={{ width: "100%", height: 420, border: 0 }} />
            ) : null}
            <div className="verify-ocr-panel">
              <p className="record-drawer-label">OCR / source text</p>
              {typeof highlightedOcr === "string" || !highlightedOcr ? (
                <pre className="verify-ocr">{extraction.ocr_text || "(no OCR text)"}</pre>
              ) : (
                <pre className="verify-ocr">
                  {highlightedOcr.before}
                  <mark className="verify-source-mark">{highlightedOcr.match}</mark>
                  {highlightedOcr.after}
                </pre>
              )}
            </div>
          </div>

          <div className="app-card" style={{ padding: 16, display: "grid", gap: 12 }}>
            <div className="row-actions" style={{ justifyContent: "space-between" }}>
              <h2 className="section-title" style={{ margin: 0 }}>
                Extracted laboratory data
              </h2>
              <StatusBadge status={extraction.status} />
            </div>
            {locked ? (
              <Notice title="Already verified">
                This extraction was promoted to Observations
                {extraction.verified_at ? ` on ${extraction.verified_at}` : ""}.
              </Notice>
            ) : null}

            {fields.map((field, index) => (
              <div
                key={`${field.name}-${index}`}
                className={`verify-field${field.confidence < 0.7 || field.require_review ? " is-low-confidence" : ""}${selectedIndex === index ? " is-selected" : ""}`}
                onClick={() => setSelectedIndex(index)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") setSelectedIndex(index);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="row-actions" style={{ justifyContent: "space-between" }}>
                  <p className="muted" style={{ margin: 0 }}>
                    {field.require_review || field.confidence < 0.7
                      ? `Needs review · confidence ${field.confidence.toFixed(2)}`
                      : `Confidence ${field.confidence.toFixed(2)}`}
                    {field.abnormal_flag_raw ? ` · flag ${field.abnormal_flag_raw}` : ""}
                    {field.source_page ? ` · page ${field.source_page}` : ""}
                  </p>
                  <StatusBadge status={field.verification_status || "pending"} />
                </div>
                <TextField
                  label="Test name"
                  value={field.name}
                  onChange={(e) => updateField(index, { name: e.target.value })}
                  disabled={locked}
                />
                <TextField
                  label="Result"
                  value={field.value}
                  onChange={(e) =>
                    updateField(index, {
                      value: e.target.value,
                      correction_reason: field.correction_reason || "reviewer_edit",
                    })
                  }
                  disabled={locked}
                />
                <div className="form-row">
                  <TextField
                    label="Unit"
                    value={field.unit}
                    onChange={(e) => updateField(index, { unit: e.target.value })}
                    disabled={locked}
                  />
                  <TextField
                    label="Reference range"
                    value={field.reference_range}
                    onChange={(e) => updateField(index, { reference_range: e.target.value })}
                    disabled={locked}
                  />
                </div>
                <TextField
                  label="Effective / collection date"
                  value={field.effective_date}
                  onChange={(e) => updateField(index, { effective_date: e.target.value })}
                  disabled={locked}
                />
                {field.source_text ? (
                  <p className="muted" style={{ fontSize: "0.8rem" }}>
                    Source evidence: {field.source_text}
                  </p>
                ) : null}
                {!locked ? (
                  <div className="row-actions">
                    <button
                      type="button"
                      className="button button-small button-light"
                      onClick={(event) => {
                        event.stopPropagation();
                        updateField(index, { verification_status: "verified" });
                      }}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="button button-small button-light"
                      onClick={(event) => {
                        event.stopPropagation();
                        updateField(index, {
                          verification_status: "rejected",
                          correction_reason: "rejected_unreadable_or_incorrect",
                        });
                      }}
                    >
                      Reject
                    </button>
                  </div>
                ) : null}
              </div>
            ))}

            <button
              type="button"
              className="button"
              disabled={pending || locked}
              onClick={() => void verify()}
            >
              {pending
                ? "Verifying…"
                : locked
                  ? "Already verified"
                  : "Verify approved rows → Observations"}
            </button>
          </div>
        </div>
      ) : (
        !problem && <p className="muted">Loading extraction…</p>
      )}
    </>
  );
}
