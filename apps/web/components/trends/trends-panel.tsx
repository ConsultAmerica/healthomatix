"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState, FormError, Notice, Table } from "@/components/ui";
import {
  apiJson,
  type InsightFlag,
  type TrendInsights,
  type TrendPoint,
  type TrendSeries,
  type TrendTest,
} from "@/lib/fhir";
import type { ApiProblem } from "@/lib/api";
import { formatDate } from "@/lib/time";
import { TrendChart } from "./trend-chart";

type Props = {
  tenantId: string;
  /** FHIR Patient id (= user id). Required for clinicians; optional for patients (self). */
  patientId?: string | null;
  title?: string;
};

function formatNum(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(digits);
}

export function TrendsPanel({ tenantId, patientId, title = "Health trends" }: Props) {
  const [tests, setTests] = useState<TrendTest[]>([]);
  const [code, setCode] = useState<string>("");
  const [series, setSeries] = useState<TrendSeries | null>(null);
  const [insights, setInsights] = useState<TrendInsights | null>(null);
  const [selected, setSelected] = useState<TrendPoint | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAllTests, setShowAllTests] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const qs = new URLSearchParams();
      if (patientId) qs.set("patient_id", patientId);
      const path = qs.toString()
        ? `/api/v1/tenants/${tenantId}/trend-tests?${qs}`
        : `/api/v1/tenants/${tenantId}/trend-tests`;
      const result = await apiJson<TrendTest[]>(path);
      if (cancelled) return;
      if (!result.ok) {
        setProblem(result.problem);
        setTests([]);
        return;
      }
      if (!result.data.length) return;
      setTests(result.data);
      const withData = result.data.find((t) => t.has_data);
      setCode((prev) => {
        if (prev && result.data.some((t) => t.code === prev)) return prev;
        return (withData ?? result.data[0]).code;
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [tenantId, patientId]);

  useEffect(() => {
    if (!code) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setProblem(null);
      setSelected(null);
      const qs = new URLSearchParams({ code });
      if (patientId) qs.set("patient_id", patientId);
      const [seriesResult, insightsResult] = await Promise.all([
        apiJson<TrendSeries>(`/api/v1/tenants/${tenantId}/trends?${qs}`),
        apiJson<TrendInsights>(`/api/v1/tenants/${tenantId}/insights?${qs}`),
      ]);
      if (cancelled) return;
      setLoading(false);
      if (!seriesResult.ok) {
        setProblem(seriesResult.problem);
        setSeries(null);
        setInsights(null);
        return;
      }
      setSeries(seriesResult.data);
      setInsights(insightsResult.ok ? insightsResult.data : null);
      if (seriesResult.data.points.length) {
        setSelected(seriesResult.data.points[seriesResult.data.points.length - 1]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenantId, patientId, code]);

  const visibleTests = useMemo(() => {
    if (showAllTests) return tests;
    const withData = tests.filter((t) => t.has_data);
    return withData.length ? withData : tests;
  }, [tests, showAllTests]);

  const consentBlocked = problem?.code === "CONSENT_DENIED";

  return (
    <section className="app-card trends-panel">
      <div className="trends-panel-header">
        <h2 className="section-title">{title}</h2>
        <div className="trends-controls">
          <label className="trends-test-select">
            <span className="visually-hidden">Lab test</span>
            <select
              value={code}
              onChange={(event) => setCode(event.target.value)}
              disabled={!visibleTests.length}
            >
              {visibleTests.map((test) => (
                <option key={test.code} value={test.code}>
                  {test.label}
                  {typeof test.point_count === "number" && test.point_count > 0
                    ? ` (${test.point_count})`
                    : ""}
                </option>
              ))}
            </select>
          </label>
          {tests.some((t) => t.has_data) && tests.some((t) => !t.has_data) ? (
            <button
              type="button"
              className="button button-small button-light"
              onClick={() => setShowAllTests((v) => !v)}
            >
              {showAllTests ? "Tests with data" : "All tests"}
            </button>
          ) : null}
        </div>
      </div>

      {consentBlocked ? (
        <Notice title="Consent required">
          Trends stay locked until this patient grants an active treatment or care-coordination
          consent. Denials are audited.
        </Notice>
      ) : (
        <Notice title="Educational context">
          Charts show verified results only. Change flags support a conversation with a clinician —
          they are not a diagnosis.
        </Notice>
      )}

      {problem && !consentBlocked ? <FormError problem={problem} /> : null}
      {loading ? <p className="muted">Loading trends…</p> : null}

      {!loading && !consentBlocked && series ? (
        <div className="trend-summary">
          <article>
            <strong>
              {formatNum(series.latest_value)} {series.unit}
            </strong>
            <span>Latest</span>
          </article>
          <article>
            <strong>
              {series.delta == null
                ? "—"
                : `${series.delta > 0 ? "+" : ""}${formatNum(series.delta)}${
                    series.delta_pct != null ? ` (${formatNum(series.delta_pct, 0)}%)` : ""
                  }`}
            </strong>
            <span>Change</span>
          </article>
          <article>
            <strong>{series.point_count ?? series.points.length}</strong>
            <span>Points</span>
          </article>
          <article>
            <strong>
              {series.reference_low != null && series.reference_high != null
                ? `${formatNum(series.reference_low)}–${formatNum(series.reference_high)}`
                : "—"}
            </strong>
            <span>Reference</span>
          </article>
        </div>
      ) : null}

      {!loading && series && !series.points.length && !consentBlocked ? (
        <EmptyState title={`No ${series.test_label.toLowerCase()} results yet`}>
          Verified lab values appear here after manual entry or document verification.
          {tests.some((t) => t.has_data && t.code !== code) ? (
            <>
              {" "}
              Try another test that already has data.
            </>
          ) : null}
        </EmptyState>
      ) : null}

      {!loading && series && series.points.length ? (
        <>
          <TrendChart
            series={series}
            selectedId={selected?.observation_id}
            onSelect={setSelected}
          />

          {selected ? (
            <div className="trend-point-detail">
              <div className="row-actions" style={{ justifyContent: "space-between" }}>
                <div>
                  <strong>
                    {selected.value} {selected.unit}
                  </strong>
                  <span className="muted"> · {formatDate(selected.effective_at)}</span>
                </div>
                {selected.in_range === false ? (
                  <span className="trend-range-badge is-out">Outside reference</span>
                ) : selected.in_range === true ? (
                  <span className="trend-range-badge">In reference</span>
                ) : null}
              </div>
              {selected.document_reference_id ? (
                <p className="muted" style={{ margin: "6px 0 0" }}>
                  Source document{" "}
                  <code className="mono">{selected.document_reference_id.slice(0, 8)}</code>
                  {selected.extraction_id
                    ? ` · extraction ${selected.extraction_id.slice(0, 8)}`
                    : ""}
                </p>
              ) : (
                <p className="muted" style={{ margin: "6px 0 0" }}>
                  Manually entered observation (no source document linked).
                </p>
              )}
            </div>
          ) : null}

          <Table caption={`${series.test_label} results`}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Value</th>
                <th scope="col">Range</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...series.points].reverse().map((point) => (
                <tr
                  key={point.observation_id}
                  className={
                    selected?.observation_id === point.observation_id ? "is-selected-row" : undefined
                  }
                  onClick={() => setSelected(point)}
                  style={{ cursor: "pointer" }}
                >
                  <td>{formatDate(point.effective_at)}</td>
                  <td>
                    {point.value} {point.unit}
                    {point.in_range === false ? (
                      <span className="trend-range-badge is-out" style={{ marginLeft: 8 }}>
                        Out
                      </span>
                    ) : null}
                  </td>
                  <td>
                    {point.reference_low != null && point.reference_high != null
                      ? `${point.reference_low}–${point.reference_high}`
                      : "—"}
                  </td>
                  <td className="mono">
                    {point.document_reference_id
                      ? point.document_reference_id.slice(0, 8)
                      : "manual"}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>

          {insights?.flags?.length ? (
            <div className="trend-insights">
              <h3 className="section-title">Change flags</h3>
              {insights.flags.map((flag: InsightFlag) => (
                <article
                  key={flag.code}
                  className={
                    flag.severity === "notable" ? "trend-insight is-notable" : "trend-insight"
                  }
                >
                  <strong>{flag.title}</strong>
                  <p>{flag.explanation}</p>
                </article>
              ))}
              <p className="muted" style={{ fontSize: "0.82rem" }}>
                {insights.disclaimer}
              </p>
            </div>
          ) : series.points.length >= 2 ? (
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              No significant change flags for this series. Keep reviewing results with your care
              team.
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
