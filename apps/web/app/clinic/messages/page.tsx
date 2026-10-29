"use client";

import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { ROLE_LABELS, useActiveMembership, usePortal } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  Section,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { apiJson } from "@/lib/fhir";
import { formatDate, shortId } from "@/lib/time";

type AiMessageDraft = {
  draft_id: string;
  category: string;
  generated_content: string;
  edited_content: string;
  status: string;
};

type Thread = Schemas["ThreadRead"];
type Message = Schemas["MessageRead"];

function senderLabel(message: Message, myUserId: string | null) {
  if (myUserId && message.sender_user_id === myUserId) return "You";
  if (message.sender_role === "patient") return "Patient";
  return ROLE_LABELS[message.sender_role ?? ""] ?? "Clinic team";
}

export default function ClinicMessagesPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <ClinicMessages />
    </RoleGate>
  );
}

function ClinicMessages() {
  const { tenant_id, tenant_name, role } = useActiveMembership();
  const { state: portalState } = usePortal();
  const myUserId = portalState.status === "ready" ? portalState.user.user_id : null;
  const canListPatients = role === "tenant_admin" || role === "staff" || role === "provider";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [patientId, setPatientId] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [aiDraft, setAiDraft] = useState<AiMessageDraft | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);

  const patients = useApiQuery(canListPatients ? `patients-for-messages:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients", { params: { path: { tenant_id } } })),
  );
  const threads = useApiQuery(`clinic-threads:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/threads", { params: { path: { tenant_id } } })),
  );
  const messages = useApiQuery(selectedId ? `clinic-messages:${tenant_id}:${selectedId}` : null, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/threads/{thread_id}/messages", {
        params: { path: { tenant_id, thread_id: selectedId! } },
      }),
    ),
  );

  async function createThread() {
    if (!subject.trim() || !body.trim() || !patientId) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/threads", {
        params: { path: { tenant_id } },
        body: { subject: subject.trim(), body: body.trim(), clinic_patient_id: patientId },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setSubject("");
    setBody("");
    setSelectedId(result.data.thread_id);
    threads.reload();
  }

  async function sendReply() {
    if (!selectedId || !reply.trim()) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/threads/{thread_id}/messages", {
        params: { path: { tenant_id, thread_id: selectedId } },
        body: { body: reply.trim() },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setReply("");
    messages.reload();
    threads.reload();
  }

  async function draftAiReply() {
    if (!selectedId) return;
    setPending(true);
    setProblem(null);
    setAiNotice(null);
    const result = await apiJson<AiMessageDraft>(
      `/api/v1/tenants/${tenant_id}/threads/${selectedId}/ai/draft-response`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setAiDraft(result.data);
    setReply(result.data.edited_content || result.data.generated_content);
    setAiNotice(`AI draft ready (${result.data.category}) — review before approve & send.`);
  }

  async function approveAndSendAiDraft() {
    if (!aiDraft) return;
    setPending(true);
    setProblem(null);
    const approved = await apiJson<AiMessageDraft>(
      `/api/v1/tenants/${tenant_id}/ai/message-drafts/${aiDraft.draft_id}/approve`,
      {
        method: "POST",
        body: JSON.stringify({ edited_content: reply.trim() || aiDraft.edited_content }),
      },
    );
    if (!approved.ok) {
      setPending(false);
      setProblem(approved.problem);
      return;
    }
    const sent = await apiJson<AiMessageDraft>(
      `/api/v1/tenants/${tenant_id}/ai/message-drafts/${aiDraft.draft_id}/send`,
      {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: `ui-${aiDraft.draft_id}`,
          body: reply.trim() || undefined,
        }),
      },
    );
    setPending(false);
    if (!sent.ok) {
      setProblem(sent.problem);
      return;
    }
    setAiDraft(sent.data);
    setReply("");
    setAiNotice("Approved AI draft sent.");
    messages.reload();
    threads.reload();
  }

  async function closeThread() {
    if (!selectedId) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/threads/{thread_id}/close", {
        params: { path: { tenant_id, thread_id: selectedId } },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    threads.reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="MESSAGES"
        title="Clinic inbox"
        description={`Secure threads with patients at ${tenant_name}.`}
      />

      <Notice title="Routine messaging only" tone="warning">
        Portal messages are not an emergency channel. Direct patients to phone or emergency services
        for urgent needs. AI may draft replies; staff must approve before send. AI never diagnoses or
        changes prescriptions.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}
      {aiNotice ? <Notice title="Messaging copilot">{aiNotice}</Notice> : null}

      <div className="split-panels">
        <Section title="Patient threads">
          <QueryView state={threads.state} onRetry={threads.reload} rows={5} loadingLabel="Loading inbox">
            {(items: Thread[]) =>
              items.length ? (
                <ul className="thread-list">
                  {items.map((thread) => (
                    <li key={thread.thread_id}>
                      <button
                        type="button"
                        className={selectedId === thread.thread_id ? "thread-item active" : "thread-item"}
                        onClick={() => setSelectedId(thread.thread_id)}
                      >
                        <strong>{thread.subject}</strong>
                        <span>
                          Patient {shortId(thread.clinic_patient_id)} · {thread.status} · {thread.message_count} messages ·{" "}
                          {formatDate(thread.updated_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="Inbox is empty">Start a conversation below or wait for a patient message.</EmptyState>
              )
            }
          </QueryView>

          <form
            className="stack-form"
            onSubmit={(event) => {
              event.preventDefault();
              void createThread();
            }}
          >
            <label>
              Patient
              {canListPatients ? (
                <select value={patientId} onChange={(event) => setPatientId(event.target.value)} required>
                  <option value="">Select patient reference</option>
                  {patients.state.status === "success"
                    ? patients.state.data.map((patient) => (
                        <option key={patient.clinic_patient_id} value={patient.clinic_patient_id}>
                          {shortId(patient.clinic_patient_id)}
                          {patient.chart_number ? ` · ${patient.chart_number}` : ""}
                        </option>
                      ))
                    : null}
                </select>
              ) : (
                <input
                  value={patientId}
                  onChange={(event) => setPatientId(event.target.value)}
                  placeholder="Clinic patient ID"
                  required
                />
              )}
            </label>
            <label>
              Subject
              <input value={subject} onChange={(event) => setSubject(event.target.value)} maxLength={200} required />
            </label>
            <label>
              Message
              <textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={4000} rows={3} required />
            </label>
            <button className="button button-small" type="submit" disabled={pending}>
              {pending ? "Sending…" : "Message patient"}
            </button>
          </form>
        </Section>

        <Section title={selectedId ? "Thread" : "Select a conversation"}>
          {!selectedId ? (
            <EmptyState title="Nothing selected">Choose a thread to reply.</EmptyState>
          ) : (
            <>
              <QueryView state={messages.state} onRetry={messages.reload} rows={5} loadingLabel="Loading thread">
                {(items: Message[]) => (
                  <ul className="message-list">
                    {items.map((message) => (
                      <li key={message.message_id} className="message-item">
                        <header>
                          <span>{senderLabel(message, myUserId)}</span>
                          <time dateTime={message.created_at}>{formatDate(message.created_at)}</time>
                        </header>
                        <p>{message.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </QueryView>
              <div className="row-actions" style={{ marginBottom: 12 }}>
                <button
                  className="button button-small button-light"
                  type="button"
                  disabled={pending}
                  onClick={() => void draftAiReply()}
                >
                  Draft AI reply
                </button>
                {aiDraft && aiDraft.status !== "sent" ? (
                  <button
                    className="button button-small"
                    type="button"
                    disabled={pending || !reply.trim()}
                    onClick={() => void approveAndSendAiDraft()}
                  >
                    Approve &amp; send AI draft
                  </button>
                ) : null}
                <button className="button button-small button-light" type="button" disabled={pending} onClick={() => void closeThread()}>
                  Close thread
                </button>
              </div>
              {aiDraft ? (
                <p className="muted" style={{ marginBottom: 8 }}>
                  Draft status <strong>{aiDraft.status}</strong> · category {aiDraft.category}
                </p>
              ) : null}
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendReply();
                }}
              >
                <label>
                  Reply
                  <textarea value={reply} onChange={(event) => setReply(event.target.value)} maxLength={4000} rows={3} required />
                </label>
                <button className="button button-small" type="submit" disabled={pending}>
                  {pending ? "Sending…" : "Send reply"}
                </button>
              </form>
            </>
          )}
        </Section>
      </div>
    </>
  );
}
