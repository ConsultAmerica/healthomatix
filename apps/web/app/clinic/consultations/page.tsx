"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  StatusBadge,
  TextField,
} from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type WaitingEntry = {
  entry_id: string;
  appointment_id: string;
  session_id?: string | null;
  patient_user_id: string;
  clinic_patient_id: string;
  status: string;
  checked_in_at?: string | null;
};

type ClinicalNote = {
  note_id: string;
  status: string;
  version: number;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  ai_assisted: boolean;
};

type FollowUpPlan = {
  plan_id: string;
  status: string;
  instructions: string;
};

/**
 * Consultation workspace — three-pane clinical layout with V1.4 waiting room,
 * SOAP notes, and clinician-approved follow-up plans.
 */
export default function ConsultationsPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <Suspense fallback={<p className="muted">Loading consultation…</p>}>
        <ConsultationWorkspace />
      </Suspense>
    </RoleGate>
  );
}

function ConsultationWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const params = useSearchParams();
  const patientId = params.get("patient");
  const appointmentId = params.get("appointment");

  const [queue, setQueue] = useState<WaitingEntry[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [connected, setConnected] = useState(false);

  const [subjective, setSubjective] = useState("");
  const [objective, setObjective] = useState("");
  const [assessment, setAssessment] = useState("");
  const [plan, setPlan] = useState("");
  const [note, setNote] = useState<ClinicalNote | null>(null);
  const [saveLabel, setSaveLabel] = useState("Save draft");
  const [followUpText, setFollowUpText] = useState("");
  const [followUpPlan, setFollowUpPlan] = useState<FollowUpPlan | null>(null);

  const activeEntry = useMemo(() => {
    if (!queue.length) return null;
    if (appointmentId) {
      return queue.find((row) => row.appointment_id === appointmentId) || null;
    }
    if (patientId) {
      return queue.find((row) => row.clinic_patient_id === patientId) || null;
    }
    return queue[0] || null;
  }, [queue, appointmentId, patientId]);

  const patientUserId = activeEntry?.patient_user_id || null;
  const clinicPatientId = activeEntry?.clinic_patient_id || patientId;
  const linkedAppointmentId = activeEntry?.appointment_id || appointmentId;
  const sessionId = activeEntry?.session_id || null;

  const loadQueue = useCallback(async () => {
    const result = await apiJson<WaitingEntry[]>(`/api/v1/tenants/${tenant_id}/waiting-room`);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setQueue(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const summaryBullets = useMemo(
    () => [
      "AI draft assistance uses authorized chart context and verified labs only (Stage A).",
      "Open the visit workspace to generate a source-linked pre-visit summary draft.",
      "Clinician must review and sign SOAP notes — AI never signs or publishes follow-up.",
      linkedAppointmentId
        ? `Linked appointment ${linkedAppointmentId.slice(0, 8)}…`
        : "Admit a waiting patient or open from schedule to bind this visit.",
    ],
    [linkedAppointmentId],
  );

  async function admit(entry: WaitingEntry) {
    setPending(true);
    setProblem(null);
    const result = await apiJson<WaitingEntry>(
      `/api/v1/tenants/${tenant_id}/appointments/${entry.appointment_id}/admit`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setNotice("Patient admitted. Open the visit workspace to join video.");
    await loadQueue();
  }

  async function saveDraft() {
    if (!patientUserId) {
      setProblem({
        kind: "invalid",
        status: 400,
        code: "PATIENT_REQUIRED",
        message: "Admit or select a waiting patient before saving a clinical note.",
        requestId: "",
        fields: {},
      });
      return;
    }
    setPending(true);
    setProblem(null);
    const body = {
      patient_id: patientUserId,
      session_id: sessionId,
      appointment_id: linkedAppointmentId,
      subjective,
      objective,
      assessment,
      plan,
      ai_assisted: false,
      expected_version: note?.version,
    };
    const result = note
      ? await apiJson<ClinicalNote>(`/api/v1/tenants/${tenant_id}/clinical-notes/${note.note_id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      : await apiJson<ClinicalNote>(`/api/v1/tenants/${tenant_id}/clinical-notes`, {
          method: "POST",
          body: JSON.stringify(body),
        });
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setNote(result.data);
    setSaveLabel("Saved");
    setNotice(`Draft note v${result.data.version} saved.`);
  }

  async function signNote() {
    if (!note) {
      await saveDraft();
      return;
    }
    setPending(true);
    setProblem(null);
    const result = await apiJson<ClinicalNote>(
      `/api/v1/tenants/${tenant_id}/clinical-notes/${note.note_id}/sign`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setNote(result.data);
    setNotice("Note signed. Further edits require an auditable amendment.");
  }

  async function createAndApproveFollowUp() {
    if (!patientUserId || !followUpText.trim()) return;
    setPending(true);
    setProblem(null);
    const created = await apiJson<FollowUpPlan>(`/api/v1/tenants/${tenant_id}/follow-up-plans`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: patientUserId,
        session_id: sessionId,
        appointment_id: linkedAppointmentId,
        instructions: followUpText.trim(),
        tasks: [],
      }),
    });
    if (!created.ok) {
      setPending(false);
      setProblem(created.problem);
      return;
    }
    const approved = await apiJson<FollowUpPlan>(
      `/api/v1/tenants/${tenant_id}/follow-up-plans/${created.data.plan_id}/approve`,
      { method: "POST", body: "{}" },
    );
    if (!approved.ok) {
      setPending(false);
      setProblem(approved.problem);
      return;
    }
    const published = await apiJson<FollowUpPlan>(
      `/api/v1/tenants/${tenant_id}/follow-up-plans/${approved.data.plan_id}/publish`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!published.ok) {
      setProblem(published.problem);
      return;
    }
    setFollowUpPlan(published.data);
    setNotice("Follow-up approved and published to the patient portal.");
  }

  return (
    <>
      <PageHeader
        eyebrow="CONSULTATION"
        title="Online consultation workspace"
        description={`${tenant_name} · waiting room, video controls, chart context, and clinician-signed documentation.`}
        actions={
          <div className="row-actions">
            {clinicPatientId ? (
              <Link className="button button-small button-light" href={`/clinic/patients/${clinicPatientId}`}>
                Open full chart
              </Link>
            ) : (
              <Link className="button button-small button-light" href="/clinic/patients">
                Choose patient
              </Link>
            )}
            <Link className="button button-small button-light" href="/clinic/doctor">
              Clinical board
            </Link>
            <Link className="button button-small button-light" href="/clinic/telehealth">
              Telehealth ops
            </Link>
          </div>
        }
      />

      <Notice title="Video & recording policy" tone="info">
        Live media uses short-lived server tokens. This build uses the Fake video adapter for demos.
        Production requires Daily, LiveKit, Vonage, or Amazon Chime under a signed BAA. Recording is
        disabled by default.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}
      {notice ? <Notice title="Update">{notice}</Notice> : null}

      <section className="app-card" style={{ padding: 16, marginBottom: 16 }} aria-label="Waiting room">
        <div className="row-actions" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <h2 className="section-title" style={{ margin: 0 }}>
            Waiting room
          </h2>
          <button className="button button-small button-light" type="button" onClick={() => void loadQueue()}>
            Refresh
          </button>
        </div>
        {queue.length ? (
          <ul className="dashboard-list">
            {queue.map((entry) => (
              <li key={entry.entry_id}>
                <div>
                  <strong>Chart {entry.clinic_patient_id.slice(0, 8)}…</strong>
                  <span className="muted">
                    Appointment {entry.appointment_id.slice(0, 8)}…
                    {entry.checked_in_at ? ` · checked in` : ""}
                  </span>
                  <StatusBadge status={entry.status} />
                </div>
                <div className="row-actions">
                  {entry.status === "waiting" || entry.status === "checked_in" ? (
                    <button
                      className="button button-small"
                      type="button"
                      disabled={pending}
                      onClick={() => void admit(entry)}
                    >
                      Admit
                    </button>
                  ) : null}
                  {entry.session_id ? (
                    <Link className="button button-small" href={`/clinic/visits/${entry.session_id}`}>
                      Open visit
                    </Link>
                  ) : null}
                  <Link
                    className="button button-small button-light"
                    href={`/clinic/patients/${entry.clinic_patient_id}`}
                  >
                    Chart
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No patients waiting">
            Patients appear here after they check in from the virtual waiting room.
          </EmptyState>
        )}
      </section>

      <div className="consult-workspace">
        <section className="consult-pane consult-media" aria-label="Patient video and controls">
          <div className={`consult-video${connected ? " is-live" : ""}`}>
            <div className="consult-video-frame">
              <p>{connected ? "Patient video · session token active" : "Waiting to connect"}</p>
              <small>
                {camOn ? "Camera on" : "Camera off"} · {micOn ? "Mic on" : "Mic muted"}
              </small>
            </div>
            <div className="consult-self-view" aria-hidden="true">
              You
            </div>
          </div>
          <div className="consult-controls">
            <button
              type="button"
              className="button button-small button-light"
              onClick={() => setMicOn((value) => !value)}
            >
              {micOn ? "Mute" : "Unmute"}
            </button>
            <button
              type="button"
              className="button button-small button-light"
              onClick={() => setCamOn((value) => !value)}
            >
              {camOn ? "Stop camera" : "Start camera"}
            </button>
            {sessionId ? (
              <Link className="button button-small" href={`/clinic/visits/${sessionId}`}>
                Join session
              </Link>
            ) : (
              <button
                type="button"
                className="button button-small"
                onClick={() => setConnected((value) => !value)}
              >
                {connected ? "End call" : "Start call"}
              </button>
            )}
          </div>
        </section>

        <section className="consult-pane consult-chart" aria-label="Patient chart context">
          <p className="section-kicker">Chart context</p>
          <h2>Patient chart · labs · documents</h2>
          {!clinicPatientId ? (
            <p className="muted">
              Admit a waiting patient or open a consultation link with a patient id.
            </p>
          ) : (
            <>
              <ul className="consult-chart-links">
                <li>
                  <Link href={`/clinic/patients/${clinicPatientId}`}>Overview &amp; timeline</Link>
                </li>
                <li>
                  <Link href={`/clinic/patients/${clinicPatientId}`}>Lab results &amp; trends</Link>
                </li>
                <li>
                  <Link href={`/clinic/patients/${clinicPatientId}`}>Medical records</Link>
                </li>
              </ul>
              <div className="consult-chart-card">
                <strong>Authorization</strong>
                <p>
                  Chart access remains consent-gated and tenant-scoped. Appointment id alone is not
                  sufficient authorization.
                </p>
              </div>
            </>
          )}
        </section>

        <section className="consult-pane consult-assist" aria-label="Clinical documentation">
          <p className="section-kicker">Documentation</p>
          <h2>SOAP note</h2>
          <ul className="previsit-bullets">
            {summaryBullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>

          {note ? <StatusBadge status={note.status} /> : null}

          <label className="consult-notes-label" htmlFor="soap-s">
            Subjective
          </label>
          <textarea
            id="soap-s"
            className="consult-notes"
            value={subjective}
            disabled={note?.status === "signed"}
            onChange={(event) => {
              setSubjective(event.target.value);
              setSaveLabel("Save draft");
            }}
            rows={3}
          />
          <label className="consult-notes-label" htmlFor="soap-o">
            Objective
          </label>
          <textarea
            id="soap-o"
            className="consult-notes"
            value={objective}
            disabled={note?.status === "signed"}
            onChange={(event) => {
              setObjective(event.target.value);
              setSaveLabel("Save draft");
            }}
            rows={3}
          />
          <label className="consult-notes-label" htmlFor="soap-a">
            Assessment
          </label>
          <textarea
            id="soap-a"
            className="consult-notes"
            value={assessment}
            disabled={note?.status === "signed"}
            onChange={(event) => {
              setAssessment(event.target.value);
              setSaveLabel("Save draft");
            }}
            rows={3}
          />
          <label className="consult-notes-label" htmlFor="soap-p">
            Plan
          </label>
          <textarea
            id="soap-p"
            className="consult-notes"
            value={plan}
            disabled={note?.status === "signed"}
            onChange={(event) => {
              setPlan(event.target.value);
              setSaveLabel("Save draft");
            }}
            rows={3}
          />

          <div className="row-actions" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="button button-small button-light"
              disabled={pending || note?.status === "signed"}
              onClick={() => void saveDraft()}
            >
              {saveLabel}
            </button>
            <button
              type="button"
              className="button button-small"
              disabled={pending || note?.status === "signed"}
              onClick={() => void signNote()}
            >
              Sign note
            </button>
          </div>

          <p className="record-drawer-label" style={{ marginTop: 16 }}>
            Follow-up (patient-visible after publish)
          </p>
          <TextField
            label="Instructions"
            value={followUpText}
            onChange={(event) => setFollowUpText(event.target.value)}
            placeholder="e.g. Return in 3 months; repeat lipid panel"
          />
          <div className="row-actions" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="button button-small"
              disabled={pending || !followUpText.trim() || !patientUserId}
              onClick={() => void createAndApproveFollowUp()}
            >
              Approve &amp; publish
            </button>
            {followUpPlan ? <StatusBadge status={followUpPlan.status} /> : null}
          </div>
        </section>
      </div>
    </>
  );
}
