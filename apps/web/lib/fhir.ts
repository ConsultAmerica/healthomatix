"use client";

import { problemFrom, type ApiProblem, type ApiResult } from "@/lib/api";

/** Session-proxied JSON helper for FHIR / intelligence routes not yet in the generated client. */
export async function apiJson<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(path, {
      ...init,
      headers: {
        "content-type": "application/json",
        "x-healthomatix-csrf": "1",
        ...(init?.headers || {}),
      },
    });
    const text = await response.text();
    const body = text ? JSON.parse(text) : null;
    if (!response.ok) {
      return {
        ok: false,
        problem: problemFrom(
          response.status,
          body,
          response.headers.get("x-request-id") ?? "",
        ),
      };
    }
    return { ok: true, data: body as T };
  } catch {
    return {
      ok: false,
      problem: {
        kind: "unavailable",
        status: 0,
        code: "NETWORK_ERROR",
        message: "The service could not be reached. Try again shortly.",
        requestId: "",
        fields: {},
      } satisfies ApiProblem,
    };
  }
}

export type FhirObservation = {
  id: string;
  resourceType: "Observation";
  status?: string;
  code?: { text?: string };
  valueQuantity?: { value?: number; unit?: string };
  valueString?: string;
  effectiveDateTime?: string;
};

export type FhirBundle = {
  resourceType: "Bundle";
  total?: number;
  entry?: Array<{ resource: FhirObservation }>;
};

export type ExtractionField = {
  name: string;
  value: string;
  unit: string;
  reference_range: string;
  effective_date: string;
  confidence: number;
  source_region: Record<string, unknown>;
  abnormal_flag_raw?: string | null;
  abnormal_flag?: string | null;
  require_review?: boolean | null;
  verification_status?: string | null;
  source_text?: string | null;
  source_page?: number | null;
  correction_reason?: string | null;
  original_extracted?: Record<string, unknown> | null;
};

export type Extraction = {
  extraction_id: string;
  document_id: string;
  document_reference_id?: string | null;
  patient_id: string;
  status: string;
  fields: ExtractionField[];
  ocr_text: string;
  created_at: string;
  verified_at?: string | null;
  processing_job_id?: string | null;
};

export type DocumentProcessingJob = {
  job_id: string;
  document_id: string;
  status: string;
  classification?: { category?: string; confidence?: number; auto_extract_lab?: boolean };
  extraction_id?: string | null;
  error_summary?: string | null;
};

export type TrendPoint = {
  observation_id: string;
  effective_at: string;
  value: number;
  unit: string;
  reference_low?: number | null;
  reference_high?: number | null;
  reference_range_text?: string;
  in_range?: boolean | null;
  document_reference_id?: string | null;
  extraction_id?: string | null;
  status?: string;
};

export type TrendSeries = {
  patient_id: string;
  test_code: string;
  test_label: string;
  unit: string;
  reference_low?: number | null;
  reference_high?: number | null;
  reference_range_text?: string;
  point_count?: number;
  latest_value?: number | null;
  latest_at?: string | null;
  previous_value?: number | null;
  delta?: number | null;
  delta_pct?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  points: TrendPoint[];
};

export type TrendTest = {
  code: string;
  label: string;
  unit: string;
  point_count?: number;
  latest_value?: number | null;
  latest_at?: string | null;
  has_data?: boolean;
};

export type InsightFlag = {
  code: string;
  severity: string;
  title: string;
  explanation: string;
  framing: string;
};

export type TrendInsights = {
  patient_id: string;
  test_code: string;
  test_label: string;
  flags: InsightFlag[];
  disclaimer: string;
  point_count?: number;
};
