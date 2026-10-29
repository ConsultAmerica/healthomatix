"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { TrendsPanel } from "@/components/trends/trends-panel";
import { FormError, Notice, PageHeader, TextField } from "@/components/ui";
import { apiJson } from "@/lib/fhir";
import type { ApiProblem } from "@/lib/api";

type SessionJoin = {
  session_id: string;
  appointment_id: string;
  status: string;
  video_provider: string;
  room_id: string;
  role: string;
  token: string;
  join_url: string;
  patient_user_id: string;
  provider_user_id: string;
  clinic_patient_id: string;
  encounter_id?: string | null;
  follow_up_plan?: string;
};

type ClinicalDraft = {
  draft_id: string;
  draft_type: string;
  status: string;
  title: string;
  content: Record<string, unknown>;
  source_links: Array<{ label?: string; reference?: string }>;
  approved_resource_id?: string | null;
};

type ClinicalNote = {
  note_id: string;
  status: string;
  version: number;
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
};

type FollowUpPlan = {
  plan_id: string;
  status: string;
  instructions: string;
};

export default function ConsultWorkspacePage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <ConsultWorkspace />
    </RoleGate>
  );
}

function ConsultWorkspace() {
  const params = useParams<{ sessionId: string }>();
  const { tenant_id } = useActiveMembership();
  const [join, setJoin] = useState<SessionJoin | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);
  const [drafts, setDrafts] = useState<ClinicalDraft[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [note, setNote] = useState<ClinicalNote | null>(null);
  const [subjective, setSubjective] = useState("");
  const [objective, setObjective] = useState("");
  const [assessment, setAssessment] = useState("");
  const [planText, setPlanText] = useState("");
  const [publishedPlan, setPublishedPlan] = useState<FollowUpPlan | null>(null);

  async function loadJoin() {
    setProblem(null);
    const result = await apiJson<SessionJoin>(
      `/api/v1/tenants/${tenant_id}/sessions/${params.sessionId}/join`,
      { method: "POST", body: "{}" },
    );
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setJoin(result.data);
    setFollowUp(result.data.follow_up_plan || "");
  }

  useEffect(() => {
    void loadJoin();
  }, [tenant_id, params.sessionId]);

  async function completeVisit() {
    if (!join) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<SessionJoin>(
      `/api/v1/tenants/${tenant_id}/sessions/${params.sessionId}/complete`,
      { method: "POST", body: JSON.stringify({ follow_up_plan: followUp }) },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setJoin({ ...join, ...result.data, status: "completed" });
    setNotice(
      `Visit completed. Encounter ${result.data.encounter_id?.slice(0, 8) ?? ""} recorded.`,
    );
  }

  async function createDraft(kind: "summaries" | "notes" | "tasks") {
    if (!join) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<ClinicalDraft>(`/api/v1/tenants/${tenant_id}/${kind}`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: join.patient_user_id,
        session_id: join.session_id,
      }),
    });
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setDrafts((prev) => [result.data, ...prev]);
    setNotice(`${result.data.title} ready for review — still a draft.`);
  }

  async function approveDraft(draftId: string) {
    setPending(true);
    setProblem(null);
    const result = await apiJson<ClinicalDraft>(
      `/api/v1/tenants/${tenant_id}/drafts/${draftId}/approve`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setDrafts((prev) => prev.map((d) => (d.draft_id === draftId ? result.data : d)));
    setNotice(`Draft approved into chart as ${result.data.approved_resource_id?.slice(0, 8)}.`);
  }

  async function saveSoapDraft() {
    if (!join) return;
    setPending(true);
    setProblem(null);
    const body = {
      patient_id: join.patient_user_id,
      session_id: join.session_id,
      appointment_id: join.appointment_id,
      subjective,
      objective,
      assessment,
      plan: planText,
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
    setNotice(`SOAP draft v${result.data.version} saved.`);
  }

  async function signSoapNote() {
    if (!note) {
      await saveSoapDraft();
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
    setNotice("SOAP note signed. Amendments require an auditable change reason.");
  }

  async function publishFollowUpPlan() {
    if (!join || !followUp.trim()) return;
    setPending(true);
    setProblem(null);
    const created = await apiJson<FollowUpPlan>(`/api/v1/tenants/${tenant_id}/follow-up-plans`, {
      method: "POST",
      body: JSON.stringify({
        patient_id: join.patient_user_id,
        session_id: join.session_id,
        appointment_id: join.appointment_id,
        instructions: followUp.trim(),
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
    setPublishedPlan(published.data);
    setNotice("Follow-up plan published to the patient visit summary.");
  }

  return (
    <>
      <PageHeader
        eyebrow="CONSULTATION"
        title="Visit workspace"
        description="Secure video session with consent-gated chart and trends. AI drafts stay out of the record until you approve them."
        actions={
          join ? (
            <Link
              className="button button-small button-light"
              href={`/clinic/patients/${join.clinic_patient_id}`}
            >
              Full chart
            </Link>
          ) : null
        }
      />

      {problem ? <FormError problem={problem} /> : null}
      {notice ? <Notice title="Update">{notice}</Notice> : null}

      {!join && !problem ? <p className="muted">Joining session…</p> : null}

      {join ? (
        <div className="consult-layout">
          <section className="app-card" style={{ padding: 16 }}>
            <h2 className="section-title">Video</h2>
            <p className="muted">
              Provider: <strong>{join.video_provider}</strong> · Room{" "}
              <code className="mono">{join.room_id}</code> · Status {join.status}
            </p>
            <Notice title="BAA boundary">
              Live video must use Daily, LiveKit, Vonage, or Amazon Chime under a signed BAA.
              This environment uses the Fake adapter for local/CI demos. Do not use Twilio
              Programmable Video.
            </Notice>
            <p className="muted" style={{ fontSize: "0.85rem", wordBreak: "break-all" }}>
              Join URL (tokenized): {join.join_url}
            </p>
            {join.status !== "completed" ? (
              <form
                className="stack-form"
                style={{ marginTop: 12 }}
                onSubmit={(event) => {
                  event.preventDefault();
                  void completeVisit();
                }}
              >
                <TextField
                  label="Follow-up plan (shared with patient after publish)"
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                />
                <div className="row-actions">
                  <button
                    className="button button-light"
                    type="button"
                    disabled={pending || !followUp.trim()}
                    onClick={() => void publishFollowUpPlan()}
                  >
                    Approve &amp; publish follow-up
                  </button>
                  <button className="button" type="submit" disabled={pending}>
                    {pending ? "Completing…" : "Complete visit & record Encounter"}
                  </button>
                </div>
                {publishedPlan ? (
                  <p className="muted" style={{ marginTop: 8 }}>
                    Published plan <code className="mono">{publishedPlan.plan_id.slice(0, 8)}</code> ·{" "}
                    {publishedPlan.status}
                  </p>
                ) : null}
              </form>
            ) : (
              <p>
                Encounter <code className="mono">{join.encounter_id}</code> recorded.
              </p>
            )}

            <h2 className="section-title" style={{ marginTop: 20 }}>
              SOAP clinical note
            </h2>
            <Notice title="Clinician accountability">
              AI drafts are optional inputs. Signing is clinician-only. Signed notes cannot be silently
              overwritten.
            </Notice>
            <label className="consult-notes-label" htmlFor="visit-s">
              Subjective
            </label>
            <textarea
              id="visit-s"
              className="consult-notes"
              rows={3}
              value={subjective}
              disabled={note?.status === "signed"}
              onChange={(e) => setSubjective(e.target.value)}
            />
            <label className="consult-notes-label" htmlFor="visit-o">
              Objective
            </label>
            <textarea
              id="visit-o"
              className="consult-notes"
              rows={3}
              value={objective}
              disabled={note?.status === "signed"}
              onChange={(e) => setObjective(e.target.value)}
            />
            <label className="consult-notes-label" htmlFor="visit-a">
              Assessment
            </label>
            <textarea
              id="visit-a"
              className="consult-notes"
              rows={3}
              value={assessment}
              disabled={note?.status === "signed"}
              onChange={(e) => setAssessment(e.target.value)}
            />
            <label className="consult-notes-label" htmlFor="visit-p">
              Plan
            </label>
            <textarea
              id="visit-p"
              className="consult-notes"
              rows={3}
              value={planText}
              disabled={note?.status === "signed"}
              onChange={(e) => setPlanText(e.target.value)}
            />
            <div className="row-actions" style={{ marginTop: 8 }}>
              <button
                type="button"
                className="button button-small button-light"
                disabled={pending || note?.status === "signed"}
                onClick={() => void saveSoapDraft()}
              >
                Save draft
              </button>
              <button
                type="button"
                className="button button-small"
                disabled={pending || note?.status === "signed"}
                onClick={() => void signSoapNote()}
              >
                Sign note
              </button>
              {note ? (
                <span className="muted">
                  {note.status} · v{note.version}
                </span>
              ) : null}
            </div>
          </section>

          <div className="consult-side">
            <TrendsPanel
              tenantId={tenant_id}
              patientId={join.patient_user_id}
              title="In-visit trends"
            />

            <section className="app-card" style={{ padding: 16, marginTop: 16 }}>
              <h2 className="section-title">AI clinical drafts</h2>
              <Notice title="Approval gate">
                Summaries, notes, and tasks are drafts. Nothing enters Clinical Records until you
                approve.
              </Notice>
              <div className="row-actions" style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="button button-small button-light"
                  disabled={pending}
                  onClick={() => void createDraft("summaries")}
                >
                  Pre-visit summary
                </button>
                <button
                  type="button"
                  className="button button-small button-light"
                  disabled={pending}
                  onClick={() => void createDraft("notes")}
                >
                  Draft note
                </button>
                <button
                  type="button"
                  className="button button-small button-light"
                  disabled={pending}
                  onClick={() => void createDraft("tasks")}
                >
                  Suggest tasks
                </button>
              </div>

              {drafts.map((draft) => (
                <article key={draft.draft_id} className="trend-insight" style={{ marginTop: 12 }}>
                  <strong>
                    {draft.title} · {draft.status}
                  </strong>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: "0.8rem",
                      marginTop: 8,
                      maxHeight: 160,
                      overflow: "auto",
                    }}
                  >
                    {JSON.stringify(draft.content, null, 2)}
                  </pre>
                  {draft.source_links?.length ? (
                    <p className="muted" style={{ fontSize: "0.8rem" }}>
                      Sources:{" "}
                      {draft.source_links
                        .map((s) => s.reference || s.label)
                        .filter(Boolean)
                        .join(", ")}
                    </p>
                  ) : null}
                  {draft.status === "draft" ? (
                    <button
                      type="button"
                      className="button button-small"
                      disabled={pending}
                      onClick={() => void approveDraft(draft.draft_id)}
                    >
                      Approve into chart
                    </button>
                  ) : (
                    <p className="muted">
                      Approved as <code className="mono">{draft.approved_resource_id}</code>
                    </p>
                  )}
                </article>
              ))}
            </section>
          </div>
        </div>
      ) : null}
    </>
  );
}
