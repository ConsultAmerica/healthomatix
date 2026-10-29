"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  SearchField,
  StatusBadge,
  Table,
  TextField,
} from "@/components/ui";
import { HealthTimeline } from "@/components/timeline/health-timeline";
import { TrendsPanel } from "@/components/trends/trends-panel";
import { api, call, useApiQuery, type ApiProblem } from "@/lib/api";
import {
  apiJson,
  type Extraction,
  type FhirBundle,
  type FhirObservation,
} from "@/lib/fhir";
import { formatDate, formatDateTime, shortId } from "@/lib/time";

type ChartTab =
  | "overview"
  | "appointments"
  | "records"
  | "messages"
  | "care"
  | "labs"
  | "medications"
  | "allergies"
  | "notes"
  | "care-plans";

const PRIMARY_TABS: Array<{ id: ChartTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "appointments", label: "Appointments" },
  { id: "records", label: "Medical Records" },
  { id: "messages", label: "Messages" },
  { id: "care", label: "Care Activities" },
];

const EXTENSION_TABS: Array<{ id: ChartTab; label: string; implemented: boolean }> = [
  { id: "labs", label: "Lab Results", implemented: true },
  { id: "medications", label: "Medications", implemented: false },
  { id: "allergies", label: "Allergies", implemented: false },
  { id: "notes", label: "Clinical Notes", implemented: false },
  { id: "care-plans", label: "Care Plans", implemented: false },
];

/* Health Trends remains available via TrendsPanel under Lab Results (verified only). */

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function observationValue(obs: FhirObservation): string {
  if (obs.valueQuantity) {
    return `${obs.valueQuantity.value ?? ""} ${obs.valueQuantity.unit ?? ""}`.trim();
  }
  return obs.valueString || "—";
}

export default function ClinicPatientDetailPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <ClinicPatientDetail />
    </RoleGate>
  );
}

function ClinicPatientDetail() {
  const params = useParams<{ clinicPatientId: string }>();
  const clinicPatientId = params.clinicPatientId;
  const { tenant_id, tenant_name } = useActiveMembership();
  const [tab, setTab] = useState<ChartTab>("overview");
  const [chartNumber, setChartNumber] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [obsCode, setObsCode] = useState("Blood pressure");
  const [obsValue, setObsValue] = useState("");
  const [obsUnit, setObsUnit] = useState("mmHg");
  const [observations, setObservations] = useState<FhirObservation[]>([]);
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [chartProblem, setChartProblem] = useState<ApiProblem | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [consentBlocked, setConsentBlocked] = useState(false);
  const [apptQuery, setApptQuery] = useState("");
  const [recordQuery, setRecordQuery] = useState("");

  const detail = useApiQuery(`patient:${tenant_id}:${clinicPatientId}`, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}", {
        params: { path: { tenant_id, clinic_patient_id: clinicPatientId } },
      }),
    ),
  );

  const patientUserId =
    detail.state.status === "success" ? detail.state.data.patient_user_id : null;

  const documents = useApiQuery(
    patientUserId && !consentBlocked ? `patient-docs:${tenant_id}:${clinicPatientId}` : null,
    () =>
      call(
        api().GET("/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}/documents", {
          params: { path: { tenant_id, clinic_patient_id: clinicPatientId } },
        }),
      ),
  );

  const appointments = useApiQuery(
    patientUserId && !consentBlocked ? `patient-appts:${tenant_id}:${clinicPatientId}` : null,
    () => {
      const from = new Date();
      from.setMonth(from.getMonth() - 3);
      const to = new Date();
      to.setMonth(to.getMonth() + 3);
      return call(
        api().GET("/api/v1/tenants/{tenant_id}/appointments", {
          params: {
            path: { tenant_id },
            query: { from: from.toISOString(), to: to.toISOString() },
          },
        }),
      );
    },
  );

  const threads = useApiQuery(
    patientUserId && !consentBlocked ? `patient-threads-chart:${tenant_id}` : null,
    () => call(api().GET("/api/v1/tenants/{tenant_id}/threads", { params: { path: { tenant_id } } })),
  );

  async function loadChart(pid: string) {
    setChartLoading(true);
    setChartProblem(null);
    const [obsResult, extResult] = await Promise.all([
      apiJson<FhirBundle>(
        `/api/v1/fhir/R4/tenants/${tenant_id}/Observation?patient=${encodeURIComponent(pid)}`,
      ),
      apiJson<Extraction[]>(
        `/api/v1/tenants/${tenant_id}/extractions?patient_id=${encodeURIComponent(pid)}`,
      ),
    ]);
    setChartLoading(false);

    if (!obsResult.ok) {
      setConsentBlocked(obsResult.problem.code === "CONSENT_DENIED");
      setChartProblem(obsResult.problem);
      setObservations([]);
      setExtractions([]);
      return;
    }
    setConsentBlocked(false);
    setObservations((obsResult.data.entry || []).map((e) => e.resource));
    if (extResult.ok) {
      setExtractions(extResult.data);
    } else {
      setExtractions([]);
    }
  }

  useEffect(() => {
    if (patientUserId) void loadChart(patientUserId);
  }, [patientUserId, tenant_id]);

  const preVisit = useMemo(() => {
    const draftCount = extractions.filter((row) => row.status === "draft").length;
    const verifiedCount = extractions.filter((row) => row.status !== "draft").length;
    const recentLabs = observations.slice(0, 5);
    return {
      draftCount,
      verifiedCount,
      recentLabs,
      bullets: [
        draftCount
          ? `${draftCount} extraction${draftCount === 1 ? "" : "s"} awaiting clinician verification`
          : "No pending document extractions",
        verifiedCount
          ? `${verifiedCount} verified extraction${verifiedCount === 1 ? "" : "s"} on file`
          : "No verified extractions yet",
        recentLabs.length
          ? `Latest observation: ${recentLabs[0].code?.text || "result"} · ${observationValue(recentLabs[0])}`
          : "No chart observations yet",
        "Consent scopes trim what appears in this workspace",
      ],
    };
  }, [extractions, observations]);

  async function saveChart() {
    setPending(true);
    setProblem(null);
    const nextChart =
      chartNumber !== null
        ? chartNumber.trim() || null
        : detail.state.status === "success"
          ? detail.state.data.chart_number
          : null;
    const result = await call(
      api().PATCH("/api/v1/tenants/{tenant_id}/patients/{clinic_patient_id}", {
        params: { path: { tenant_id, clinic_patient_id: clinicPatientId } },
        body: { chart_number: nextChart },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setChartNumber(null);
    detail.reload();
  }

  async function addObservation() {
    if (!patientUserId || !obsValue.trim()) return;
    setPending(true);
    setChartProblem(null);
    const numeric = Number(obsValue);
    const body =
      Number.isFinite(numeric) && obsValue.trim() !== ""
        ? {
            resourceType: "Observation",
            status: "final",
            code: { text: obsCode },
            subject: { reference: `Patient/${patientUserId}` },
            valueQuantity: { value: numeric, unit: obsUnit },
          }
        : {
            resourceType: "Observation",
            status: "final",
            code: { text: obsCode },
            subject: { reference: `Patient/${patientUserId}` },
            valueString: obsValue,
          };
    const result = await apiJson<FhirObservation>(
      `/api/v1/fhir/R4/tenants/${tenant_id}/Observation`,
      { method: "POST", body: JSON.stringify(body) },
    );
    setPending(false);
    if (!result.ok) {
      setConsentBlocked(result.problem.code === "CONSENT_DENIED");
      setChartProblem(result.problem);
      return;
    }
    setObsValue("");
    void loadChart(patientUserId);
  }

  async function startExtraction(documentId: string) {
    if (!patientUserId) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<{ extraction_id: string }>(
      `/api/v1/tenants/${tenant_id}/documents/${documentId}/extractions`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    window.location.href = `/clinic/patients/${clinicPatientId}/verify/${result.data.extraction_id}`;
  }

  async function downloadDocument(documentId: string, filename: string) {
    setPending(true);
    setProblem(null);
    try {
      const response = await fetch(
        `/api/v1/tenants/${tenant_id}/documents/${documentId}/content`,
        { headers: { "x-healthomatix-csrf": "1" } },
      );
      if (!response.ok) {
        const text = await response.text();
        let body: unknown = null;
        try {
          body = text ? JSON.parse(text) : null;
        } catch {
          body = null;
        }
        const { problemFrom } = await import("@/lib/api");
        setProblem(
          problemFrom(response.status, body, response.headers.get("x-request-id") ?? ""),
        );
        setPending(false);
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
      setProblem({
        kind: "unavailable",
        status: 0,
        code: "NETWORK_ERROR",
        message: "The document could not be downloaded. Try again shortly.",
        requestId: "",
        fields: {},
      });
    }
    setPending(false);
  }

  const patientAppointments =
    appointments.state.status === "success"
      ? appointments.state.data.filter((row) => row.clinic_patient_id === clinicPatientId)
      : [];

  const filteredAppointments = patientAppointments.filter((row) => {
    const needle = apptQuery.trim().toLowerCase();
    if (!needle) return true;
    return `${row.provider_name || ""} ${row.location_name || ""} ${row.status}`
      .toLowerCase()
      .includes(needle);
  });

  return (
    <>
      <PageHeader
        eyebrow="PATIENT CHART"
        title={
          detail.state.status === "success"
            ? detail.state.data.chart_number || "Patient workspace"
            : "Patient workspace"
        }
        description={`Authorized chart for ${tenant_name}. Demographics, visits, records, and messages stay within your clinic membership.`}
        actions={
          <div className="row-actions">
            <Link
              className="button button-small"
              href={`/clinic/consultations?patient=${clinicPatientId}`}
            >
              Open consultation
            </Link>
            <Link className="button button-small button-light" href="/clinic/messages">
              Messages
            </Link>
            <Link className="button button-small button-light" href="/clinic/patients">
              Back to roster
            </Link>
          </div>
        }
      />

      {problem ? <FormError problem={problem} /> : null}

      <QueryView state={detail.state} onRetry={detail.reload} rows={3} loadingLabel="Loading patient">
        {(patient) => (
          <header className="patient-chart-header app-card">
            <div className="metric-strip">
              <article>
                <strong>{patient.chart_number || "Not assigned"}</strong>
                <span>Clinic chart ID</span>
              </article>
              <article>
                <strong className="mono">{shortId(patient.clinic_patient_id)}</strong>
                <span>Internal reference</span>
              </article>
              <article>
                <StatusBadge status={patient.status} />
                <span>Relationship</span>
              </article>
              <article>
                <strong>{formatDate(patient.created_at)}</strong>
                <span>Linked</span>
              </article>
            </div>
            <p className="muted chart-header-note">
              Contact details appear only when permitted by membership and consent. Prefer chart
              number over patient identifiers in shared spaces.
            </p>
          </header>
        )}
      </QueryView>

      {consentBlocked ? (
        <Notice title="Consent required" tone="warning">
          This patient has not granted an active treatment or care-coordination consent, or they
          withdrew it. Chart, documents, and extractions stay locked until they grant consent again.
        </Notice>
      ) : (
        <Notice title="Consent gate">
          Observations and documents load only when the patient has granted an active treatment or
          care-coordination consent. Denials are audited.
        </Notice>
      )}

      {chartProblem && !consentBlocked ? <FormError problem={chartProblem} /> : null}

      <div className="chart-workspace">
        <div className="chart-main">
          <div className="chart-tabs" role="tablist" aria-label="Patient chart sections">
            {PRIMARY_TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className={`chart-tab${tab === item.id ? " is-active" : ""}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="chart-tabs chart-tabs-secondary" role="tablist" aria-label="Clinical extensions">
            {EXTENSION_TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className={`chart-tab${tab === item.id ? " is-active" : ""}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {!item.implemented ? <span className="chart-tab-planned">Planned</span> : null}
              </button>
            ))}
          </div>

          <div className="chart-panel" role="tabpanel">
            {tab === "overview" ? (
              <>
                <QueryView state={detail.state} onRetry={detail.reload} rows={2}>
                  {(patient) => (
                    <form
                      className="stack-form app-card"
                      style={{ marginBottom: 16, padding: 16 }}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void saveChart();
                      }}
                    >
                      <h2 className="section-title">Demographics &amp; clinic relationship</h2>
                      <TextField
                        label="Chart number"
                        value={chartNumber ?? patient.chart_number ?? ""}
                        onChange={(event) => setChartNumber(event.target.value)}
                        maxLength={96}
                        hint="Clinic-assigned identifier only."
                      />
                      <p className="muted">
                        Status: <StatusBadge status={patient.status} /> · Linked{" "}
                        {formatDate(patient.created_at)}
                      </p>
                      <button className="button button-small" type="submit" disabled={pending}>
                        {pending ? "Saving…" : "Save chart number"}
                      </button>
                    </form>
                  )}
                </QueryView>

                {!consentBlocked ? (
                  <section className="app-card" style={{ padding: 16, marginBottom: 16 }}>
                    <h2 className="section-title">Recent activity</h2>
                    <HealthTimeline
                      path={`/api/v1/tenants/${tenant_id}/patients/${clinicPatientId}/timeline`}
                      base="clinic"
                      clinicPatientId={clinicPatientId}
                    />
                  </section>
                ) : null}
              </>
            ) : null}

            {tab === "appointments" ? (
              <section className="app-card" style={{ padding: 16 }}>
                <h2 className="section-title">Appointments</h2>
                <p className="muted">Previous and upcoming visits for this clinic patient.</p>
                {consentBlocked ? (
                  <EmptyState title="Appointments locked by consent" />
                ) : (
                  <>
                    <SearchField
                      label="Search appointments"
                      value={apptQuery}
                      onChange={setApptQuery}
                      placeholder="Search provider, location, status…"
                    />
                    <QueryView
                      state={appointments.state}
                      onRetry={appointments.reload}
                      rows={3}
                      loadingLabel="Loading appointments"
                    >
                      {() =>
                        filteredAppointments.length ? (
                          <Table caption="Patient appointments">
                            <thead>
                              <tr>
                                <th scope="col">When</th>
                                <th scope="col">Provider</th>
                                <th scope="col">Location</th>
                                <th scope="col">Status</th>
                                <th scope="col">Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {filteredAppointments.map((row) => (
                                <tr key={row.appointment_id}>
                                  <td>{formatDateTime(row.starts_at, row.timezone)}</td>
                                  <td>{row.provider_name || "—"}</td>
                                  <td>{row.location_name || "—"}</td>
                                  <td>
                                    <StatusBadge status={row.status} />
                                  </td>
                                  <td>
                                    <Link
                                      className="button button-small button-light"
                                      href={`/clinic/consultations?patient=${clinicPatientId}&appointment=${row.appointment_id}`}
                                    >
                                      Prepare visit
                                    </Link>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </Table>
                        ) : (
                          <EmptyState title="No matching appointments">
                            Book from the schedule, then return here for visit context.
                          </EmptyState>
                        )
                      }
                    </QueryView>
                  </>
                )}
              </section>
            ) : null}

            {tab === "records" ? (
              consentBlocked ? (
                <EmptyState title="Documents locked">
                  Ask the patient to grant chart consent from Profile &amp; consent in their portal.
                </EmptyState>
              ) : (
                <>
                  <SearchField
                    label="Search medical records"
                    value={recordQuery}
                    onChange={setRecordQuery}
                    placeholder="Search by file name…"
                  />
                  <QueryView
                    state={documents.state}
                    onRetry={documents.reload}
                    rows={4}
                    loadingLabel="Loading document metadata"
                  >
                    {(rows) => {
                      const needle = recordQuery.trim().toLowerCase();
                      const filtered = rows.filter(
                        (document) =>
                          !needle || document.original_filename.toLowerCase().includes(needle),
                      );
                      return filtered.length ? (
                        <Table caption="Medical records">
                          <thead>
                            <tr>
                              <th scope="col">Name</th>
                              <th scope="col">Type</th>
                              <th scope="col">Size</th>
                              <th scope="col">Added</th>
                              <th scope="col">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filtered.map((document) => (
                              <tr key={document.document_id}>
                                <td>
                                  <strong className="cell-title">{document.original_filename}</strong>
                                </td>
                                <td>{document.content_type}</td>
                                <td>{formatBytes(document.size_bytes)}</td>
                                <td>{formatDate(document.created_at)}</td>
                                <td>
                                  <div className="row-actions">
                                    <button
                                      type="button"
                                      className="button button-small button-light"
                                      disabled={pending}
                                      onClick={() =>
                                        void downloadDocument(
                                          document.document_id,
                                          document.original_filename,
                                        )
                                      }
                                    >
                                      Download
                                    </button>
                                    <button
                                      type="button"
                                      className="button button-small button-light"
                                      disabled={pending}
                                      onClick={() => void startExtraction(document.document_id)}
                                    >
                                      Extract &amp; verify
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </Table>
                      ) : (
                        <EmptyState title="No documents on file">
                          When the patient uploads records, metadata appears here.
                        </EmptyState>
                      );
                    }}
                  </QueryView>
                </>
              )
            ) : null}

            {tab === "messages" ? (
              <section className="app-card" style={{ padding: 16 }}>
                <h2 className="section-title">Authorized conversations</h2>
                <p className="muted">
                  Routine messaging is not for emergencies. Threads listed here are tenant-scoped
                  clinic conversations you are permitted to open.
                </p>
                {consentBlocked ? (
                  <EmptyState title="Messages locked by consent" />
                ) : (
                  <QueryView
                    state={threads.state}
                    onRetry={threads.reload}
                    rows={3}
                    loadingLabel="Loading conversations"
                  >
                    {(rows) =>
                      rows.length ? (
                        <ul className="dashboard-list">
                          {rows.slice(0, 10).map((thread) => (
                            <li key={thread.thread_id}>
                              <div>
                                <strong>{thread.subject || "Conversation"}</strong>
                                <span className="muted">
                                  {thread.message_count} message
                                  {thread.message_count === 1 ? "" : "s"} · updated{" "}
                                  {formatDate(thread.updated_at)}
                                </span>
                              </div>
                              <Link className="button button-small button-light" href="/clinic/messages">
                                Open inbox
                              </Link>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <EmptyState title="No conversations yet">
                          <Link className="button button-small" href="/clinic/messages">
                            Go to messages
                          </Link>
                        </EmptyState>
                      )
                    }
                  </QueryView>
                )}
              </section>
            ) : null}

            {tab === "care" ? (
              <section className="app-card" style={{ padding: 16 }}>
                <h2 className="section-title">Care activities</h2>
                <p className="muted">
                  Follow-ups and administrative tasks supported by current persistence. Unsupported
                  clinical task types are not fabricated here.
                </p>
                <ul className="dashboard-list">
                  {patientAppointments
                    .filter((row) => row.status === "booked")
                    .slice(0, 5)
                    .map((row) => (
                      <li key={`care-${row.appointment_id}`}>
                        <div>
                          <strong>Upcoming visit</strong>
                          <span className="muted">
                            {formatDateTime(row.starts_at, row.timezone)} ·{" "}
                            {row.provider_name || "Provider"}
                          </span>
                        </div>
                        <Link
                          className="button button-small button-light"
                          href={`/clinic/consultations?patient=${clinicPatientId}&appointment=${row.appointment_id}`}
                        >
                          Prepare
                        </Link>
                      </li>
                    ))}
                  {extractions
                    .filter((row) => row.status === "draft")
                    .slice(0, 5)
                    .map((row) => (
                      <li key={`ext-${row.extraction_id}`}>
                        <div>
                          <strong>Document review</strong>
                          <span className="muted">
                            {row.fields.length} fields · {formatDate(row.created_at)}
                          </span>
                        </div>
                        <Link
                          className="button button-small button-light"
                          href={`/clinic/patients/${clinicPatientId}/verify/${row.extraction_id}`}
                        >
                          Review
                        </Link>
                      </li>
                    ))}
                </ul>
                {!patientAppointments.some((row) => row.status === "booked") &&
                !extractions.some((row) => row.status === "draft") ? (
                  <EmptyState title="No open care activities">
                    Booked visits and draft extractions appear here when present.
                  </EmptyState>
                ) : null}
              </section>
            ) : null}

            {tab === "labs" ? (
              <>
                <Notice title="Verified laboratory workspace">
                  Only clinician-verified Observations appear below and in Health Trends. Draft
                  extractions stay in the review queue until approved, corrected, or rejected with
                  source evidence.
                </Notice>
                <section className="app-card" style={{ padding: 16, marginBottom: 16 }}>
                  <h2 className="section-title">Verified lab results</h2>
                  {chartLoading ? <p className="muted">Loading chart…</p> : null}
                  {observations.length ? (
                    <Table caption="Lab observations">
                      <thead>
                        <tr>
                          <th scope="col">Test</th>
                          <th scope="col">Value</th>
                          <th scope="col">Effective</th>
                          <th scope="col">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {observations.map((obs) => (
                          <tr key={obs.id}>
                            <td>{obs.code?.text || obs.id}</td>
                            <td>{observationValue(obs)}</td>
                            <td>{obs.effectiveDateTime || "—"}</td>
                            <td>{obs.status || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  ) : (
                    !chartLoading &&
                    !consentBlocked && (
                      <EmptyState title="No observations yet">
                        Enter a result below, or verify an uploaded document.
                      </EmptyState>
                    )
                  )}

                  {!consentBlocked ? (
                    <form
                      className="stack-form"
                      style={{ marginTop: 16 }}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void addObservation();
                      }}
                    >
                      <TextField label="Observation" value={obsCode} onChange={(e) => setObsCode(e.target.value)} />
                      <TextField label="Value" value={obsValue} onChange={(e) => setObsValue(e.target.value)} />
                      <TextField label="Unit" value={obsUnit} onChange={(e) => setObsUnit(e.target.value)} />
                      <button className="button button-small" type="submit" disabled={pending || !patientUserId}>
                        Add observation
                      </button>
                    </form>
                  ) : null}
                </section>

                {!consentBlocked && extractions.length ? (
                  <section className="app-card" style={{ padding: 16, marginBottom: 16 }}>
                    <h2 className="section-title">Extractions to verify</h2>
                    <Table caption="Document extractions">
                      <thead>
                        <tr>
                          <th scope="col">Status</th>
                          <th scope="col">Fields</th>
                          <th scope="col">Created</th>
                          <th scope="col">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {extractions.map((row) => (
                          <tr key={row.extraction_id}>
                            <td>
                              <StatusBadge status={row.status} />
                            </td>
                            <td>{row.fields.length}</td>
                            <td>{formatDate(row.created_at)}</td>
                            <td>
                              {row.status === "draft" ? (
                                <Link
                                  className="button button-small button-light"
                                  href={`/clinic/patients/${clinicPatientId}/verify/${row.extraction_id}`}
                                >
                                  Continue review
                                </Link>
                              ) : (
                                <span className="muted">
                                  Verified {row.verified_at ? formatDate(row.verified_at) : ""}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </section>
                ) : null}

                {!consentBlocked && patientUserId ? (
                  <TrendsPanel tenantId={tenant_id} patientId={patientUserId} title="Lab trends" />
                ) : null}
              </>
            ) : null}

            {tab === "medications" ? (
              <EmptyState title="Medications — planned">
                Medication list persistence and pharmacy edge scopes are not production-ready in
                V1.2. This tab is an extension point only.
              </EmptyState>
            ) : null}

            {tab === "allergies" ? (
              <EmptyState title="Allergies — planned">
                Dedicated allergy list storage is not wired. Capture allergies in consultation notes
                until the allergy module ships.
              </EmptyState>
            ) : null}

            {tab === "notes" ? (
              <section className="app-card" style={{ padding: 16 }}>
                <h2 className="section-title">Clinical notes</h2>
                <p className="muted">
                  Signed clinical note storage is not presented as complete here. Use the
                  consultation workspace for draft visit capture in the demo path.
                </p>
                <Link
                  className="button button-small"
                  href={`/clinic/consultations?patient=${clinicPatientId}`}
                >
                  Open consultation workspace
                </Link>
              </section>
            ) : null}

            {tab === "care-plans" ? (
              <EmptyState title="Care plans — planned">
                Approved follow-up care plans will list here after dedicated plan persistence ships.
              </EmptyState>
            ) : null}
          </div>
        </div>

        <aside className="previsit-panel" aria-label="Pre-visit context">
          <p className="section-kicker">Pre-visit context</p>
          <h2>Visit briefing</h2>
          <p className="muted">
            Source-linked chart highlights for the next encounter. Not an autonomous clinical
            decision. AI narrative summaries remain a later increment.
          </p>
          <ul className="previsit-bullets">
            {preVisit.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
          <div className="previsit-sources">
            <p className="record-drawer-label">Sources</p>
            <ul>
              <li>
                <button type="button" className="text-button" onClick={() => setTab("labs")}>
                  Lab Results ({observations.length})
                </button>
              </li>
              <li>
                <button type="button" className="text-button" onClick={() => setTab("records")}>
                  Medical Records
                </button>
              </li>
              <li>
                <button type="button" className="text-button" onClick={() => setTab("overview")}>
                  Health Timeline
                </button>
              </li>
            </ul>
          </div>
          <Link
            className="button button-small"
            href={`/clinic/consultations?patient=${clinicPatientId}`}
          >
            Start consultation
          </Link>
        </aside>
      </div>
    </>
  );
}
