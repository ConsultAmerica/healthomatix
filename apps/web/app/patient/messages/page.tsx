"use client";

import { useState } from "react";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  EmptyState,
  FormError,
  PageHeader,
  QueryView,
  Section,
} from "@/components/ui";
import { api, call, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDate } from "@/lib/time";

type Thread = Schemas["ThreadRead"];
type Message = Schemas["MessageRead"];

export default function MessagesPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [reply, setReply] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const threads = useApiQuery(`threads:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/threads", { params: { path: { tenant_id } } })),
  );
  const messages = useApiQuery(selectedId ? `messages:${tenant_id}:${selectedId}` : null, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/threads/{thread_id}/messages", {
        params: { path: { tenant_id, thread_id: selectedId! } },
      }),
    ),
  );

  async function createThread() {
    if (!subject.trim() || !body.trim()) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/threads", {
        params: { path: { tenant_id } },
        body: { subject: subject.trim(), body: body.trim() },
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
    messages.reload();
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

  return (
    <>
      <PageHeader
        eyebrow="MESSAGES"
        title="Secure messages"
        description={`Message your care team at ${tenant_name}.`}
      />

      {problem ? <FormError problem={problem} /> : null}

      <div className="split-panels">
        <Section title="Conversations">
          <QueryView state={threads.state} onRetry={threads.reload} rows={4} loadingLabel="Loading messages">
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
                          {thread.message_count} message{thread.message_count === 1 ? "" : "s"} ·{" "}
                          {formatDate(thread.updated_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No conversations yet">
                  Start a thread below to reach your clinic.
                </EmptyState>
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
              Subject
              <input
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                maxLength={200}
                required
              />
            </label>
            <label>
              Message
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                maxLength={4000}
                rows={4}
                required
              />
            </label>
            <button className="button button-small" type="submit" disabled={pending}>
              {pending ? "Sending…" : "Start conversation"}
            </button>
          </form>
        </Section>

        <Section title={selectedId ? "Thread" : "Select a conversation"}>
          {!selectedId ? (
            <EmptyState title="Nothing selected">Choose a conversation to read and reply.</EmptyState>
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
                          <span className="mono">{message.sender_user_id.slice(0, 8)}</span>
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
