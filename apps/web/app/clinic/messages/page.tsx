"use client";

import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  PageHeader,
  QueryView,
  Section,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDate, shortId } from "@/lib/time";

type Thread = Schemas["ThreadRead"];
type Message = Schemas["MessageRead"];

export default function ClinicMessagesPage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <ClinicMessages />
    </RoleGate>
  );
}

function ClinicMessages() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

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

  return (
    <>
      <PageHeader
        eyebrow="MESSAGES"
        title="Clinic inbox"
        description={`Secure threads from patients at ${tenant_name}.`}
      />

      {problem ? <FormError problem={problem} /> : null}

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
                          Patient {shortId(thread.clinic_patient_id)} · {thread.message_count} messages ·{" "}
                          {formatDate(thread.updated_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="Inbox is empty">
                  When patients start a conversation, it appears here.
                </EmptyState>
              )
            }
          </QueryView>
        </Section>

        <Section title={selectedId ? "Thread" : "Select a conversation"}>
          {!selectedId ? (
            <EmptyState title="Nothing selected">Choose a thread to reply.</EmptyState>
          ) : (
            <>
              <QueryView
                state={messages.state}
                onRetry={messages.reload}
                rows={5}
                loadingLabel="Loading thread"
              >
                {(items: Message[]) => (
                  <ul className="message-list">
                    {items.map((message) => (
                      <li key={message.message_id} className="message-item">
                        <header>
                          <span className="mono">{shortId(message.sender_user_id)}</span>
                          <time dateTime={message.created_at}>{formatDate(message.created_at)}</time>
                        </header>
                        <p>{message.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </QueryView>
              <form
                className="stack-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendReply();
                }}
              >
                <label>
                  Reply
                  <textarea
                    value={reply}
                    onChange={(event) => setReply(event.target.value)}
                    maxLength={4000}
                    rows={3}
                    required
                  />
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
