"use client";

import Link from "next/link";
import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section, StatusBadge, TextField } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type ScribeSession = {
  scribe_session_id: string;
  mode: string;
  status: string;
  speech_provider: string;
  consent_grant_id?: string | null;
};

type TranscriptSegment = {
  segment_id: string;
  speaker_label: string;
  transcript_text: string;
};

type SoapDraft = {
  generation_id: string;
  draft_id?: string | null;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  disclaimer: string;
  source_links: Array<{ label?: string; reference?: string }>;
};

export default function AiScribePage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <AiScribeWorkspace />
    </RoleGate>
  );
}

function AiScribeWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [patientId, setPatientId] = useState("");
  const [mode, setMode] = useState<"manual" | "ambient">("manual");
  const [visitReason, setVisitReason] = useState("");
  const [clinicianNotes, setClinicianNotes] = useState("");
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [soap, setSoap] = useState<SoapDraft | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);

  async function startSession() {
    if (!patientId.trim()) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<ScribeSession>(`/api/v1/tenants/${tenant_id}/scribe/sessions`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: patientId.trim(),
        mode,
        visit_reason: visitReason,
        clinician_notes: clinicianNotes,
      }),
    });
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setSession(result.data);
    setSoap(null);
    if (result.data.mode === "ambient") {
      const transcript = await apiJson<TranscriptSegment[]>(
        `/api/v1/tenants/${tenant_id}/scribe/sessions/${result.data.scribe_session_id}/transcript`,
      );
      if (transcript.ok) setSegments(transcript.data);
    } else {
      setSegments([]);
    }
  }

  async function stopSession() {
    if (!session) return;
    setPending(true);
    const result = await apiJson<ScribeSession>(
      `/api/v1/tenants/${tenant_id}/scribe/sessions/${session.scribe_session_id}/stop`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setSession(result.data);
  }

  async function generateNote() {
    if (!session) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<SoapDraft>(
      `/api/v1/tenants/${tenant_id}/scribe/sessions/${session.scribe_session_id}/generate-note`,
      {
        method: "POST",
        body: JSON.stringify({ visit_reason: visitReason, clinician_notes: clinicianNotes }),
      },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setSoap(result.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="AI SCRIBE"
        title="Medical scribe"
        description={`${tenant_name} · Mode A manual drafts always available. Mode B ambient STT requires explicit ai_scribe consent.`}
        actions={
          <Link className="button button-small button-light" href="/clinic/consultations">
            Consultation workspace
          </Link>
        }
      />

      <Notice title="Clinician accountability">
        AI drafts do not diagnose, prescribe, or sign notes. Ambient capture uses the Fake speech
        adapter in demos—no raw audio is stored. Recording indicators must remain visible when live
        STT is configured under a BAA.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Session controls">
        <div className="stack-form">
          <TextField
            label="Patient user ID"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="36-character patient user id"
          />
          <label className="field">
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value as "manual" | "ambient")}>
              <option value="manual">Manual clinical scribe (no audio)</option>
              <option value="ambient">Ambient AI scribe (consent required)</option>
            </select>
          </label>
          <TextField
            label="Visit reason"
            value={visitReason}
            onChange={(e) => setVisitReason(e.target.value)}
          />
          <label className="field">
            Clinician notes
            <textarea
              value={clinicianNotes}
              onChange={(e) => setClinicianNotes(e.target.value)}
              rows={4}
            />
          </label>
          <div className="row-actions">
            <button className="button" type="button" disabled={pending} onClick={() => void startSession()}>
              Start scribe
            </button>
            {session && session.status !== "stopped" ? (
              <button
                className="button button-light"
                type="button"
                disabled={pending}
                onClick={() => void stopSession()}
              >
                Stop
              </button>
            ) : null}
            {session ? (
              <button
                className="button button-light"
                type="button"
                disabled={pending}
                onClick={() => void generateNote()}
              >
                Generate SOAP draft
              </button>
            ) : null}
          </div>
        </div>
        {session ? (
          <p className="muted" style={{ marginTop: 12 }}>
            Session <code className="mono">{session.scribe_session_id.slice(0, 8)}</code> ·{" "}
            <StatusBadge status={session.status} /> · {session.mode} · {session.speech_provider}
            {session.consent_grant_id ? " · consent linked" : ""}
          </p>
        ) : null}
      </Section>

      {segments.length ? (
        <Section title="Transcript review">
          <ul className="dashboard-list">
            {segments.map((seg) => (
              <li key={seg.segment_id}>
                <div>
                  <strong>{seg.speaker_label}</strong>
                  <span>{seg.transcript_text}</span>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {soap ? (
        <Section title="SOAP draft (editable elsewhere before sign)">
          <Notice title="AI-assisted draft">{soap.disclaimer}</Notice>
          <p>
            <strong>S</strong> {soap.subjective}
          </p>
          <p>
            <strong>O</strong> {soap.objective}
          </p>
          <p>
            <strong>A</strong> {soap.assessment}
          </p>
          <p>
            <strong>P</strong> {soap.plan}
          </p>
          {soap.source_links?.length ? (
            <p className="muted">
              Sources:{" "}
              {soap.source_links
                .map((s) => s.reference || s.label)
                .filter(Boolean)
                .join(", ")}
            </p>
          ) : null}
          <Link className="button button-small" href="/clinic/consultations">
            Open note editor / quality check
          </Link>
        </Section>
      ) : null}
    </>
  );
}
