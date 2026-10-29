"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AppointmentItem } from "@/components/appointments";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { HealthTimeline } from "@/components/timeline/health-timeline";
import {
  Card,
  DashboardGrid,
  EmptyState,
  Notice,
  PageHeader,
  QueryView,
  SearchField,
  Section,
  StatusBadge,
} from "@/components/ui";
import { api, call, callOptional, useApiQuery } from "@/lib/api";
import { formatDate, formatDateTime, isFuture, timeZoneLabel } from "@/lib/time";

function todayLabel(): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date());
}

export default function PatientHomePage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const scheduling = features?.schedulingEnabled ?? false;
  const path = { params: { path: { tenant_id } } };
  const [recordQuery, setRecordQuery] = useState("");
  const [messageQuery, setMessageQuery] = useState("");

  const appointments = useApiQuery(scheduling ? `my-appointments:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/appointments", path)),
  );
  const documents = useApiQuery(`documents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/documents", path)),
  );
  const threads = useApiQuery(`threads-home:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/threads", path)),
  );
  const profile = useApiQuery(`patient-profile:${tenant_id}`, () =>
    callOptional(api().GET("/api/v1/tenants/{tenant_id}/patients/me", path), "PROFILE_NOT_FOUND"),
  );

  const upcoming =
    appointments.state.status === "success"
      ? appointments.state.data
          .filter((item) => item.status === "booked" && isFuture(item.starts_at))
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      : [];
  const next = upcoming[0] ?? null;

  const recentDocs = useMemo(() => {
    if (documents.state.status !== "success") return [];
    const needle = recordQuery.trim().toLowerCase();
    return documents.state.data
      .filter((doc) => !needle || doc.original_filename.toLowerCase().includes(needle))
      .slice(0, 5);
  }, [documents.state, recordQuery]);

  const recentThreads = useMemo(() => {
    if (threads.state.status !== "success") return [];
    const needle = messageQuery.trim().toLowerCase();
    return threads.state.data
      .filter((thread) => thread.status === "open")
      .filter((thread) => !needle || (thread.subject || "").toLowerCase().includes(needle))
      .slice(0, 5);
  }, [threads.state, messageQuery]);

  const name = profile.state.status === "success" ? profile.state.data?.preferred_name : "";
  const profileIncomplete = profile.state.status === "success" && !profile.state.data;
  const openMessageCount =
    threads.state.status === "success"
      ? threads.state.data.filter((thread) => thread.status === "open").length
      : 0;

  const careActivities = [
    ...(next
      ? [
          {
            id: "follow-up",
            title: `Upcoming visit with ${next.provider_name}`,
            detail: formatDateTime(next.starts_at, next.timezone),
            href: "/patient/appointments",
          },
        ]
      : []),
    ...(profileIncomplete
      ? [
          {
            id: "profile",
            title: "Complete your patient profile",
            detail: "Preferred name and contact details help your clinic reach you.",
            href: "/patient/profile",
          },
        ]
      : []),
    ...(openMessageCount
      ? [
          {
            id: "messages",
            title: `${openMessageCount} open conversation${openMessageCount === 1 ? "" : "s"}`,
            detail: "Review clinic messages when you have a moment.",
            href: "/patient/messages",
          },
        ]
      : []),
    {
      id: "records",
      title: "Keep medical records current",
      detail: "Upload lab reports before your next visit when available.",
      href: "/patient/records",
    },
  ];

  const attentionItems = [
    ...(next
      ? [`Confirmed visit on ${formatDate(next.starts_at, next.timezone)} with ${next.provider_name}.`]
      : []),
    ...(openMessageCount ? [`You have ${openMessageCount} open clinic conversation(s).`] : []),
    ...(profileIncomplete ? ["Your patient profile still needs basic details."] : []),
  ];

  return (
    <>
      <PageHeader
        eyebrow={tenant_name.toUpperCase()}
        title={name ? `Welcome back, ${name}` : "Welcome back"}
        description={
          <>
            <span className="dashboard-date">{todayLabel()}</span>
            {" · "}Your upcoming visit, records, messages, and care activities.
          </>
        }
        actions={
          <div className="row-actions">
            {attentionItems.length ? (
              <span
                className="notification-chip"
                title={attentionItems.join(" ")}
                aria-label={`${attentionItems.length} live updates from appointments and messages`}
              >
                {attentionItems.length} update{attentionItems.length === 1 ? "" : "s"}
              </span>
            ) : null}
            <Link className="button button-small button-light" href="/patient/profile">
              Profile
            </Link>
            {scheduling ? (
              <Link className="button button-small" href="/patient/care">
                Book appointment
              </Link>
            ) : null}
          </div>
        }
      />

      {profileIncomplete ? (
        <Notice title="Finish setting up your profile">
          Tell your clinic what to call you and how to reach you.{" "}
          <Link href="/patient/profile">Complete profile</Link>
        </Notice>
      ) : null}

      <Notice title="Messaging is not for emergencies" tone="warning">
        If you need urgent care, contact emergency services or your clinic by phone. Portal messages are for
        routine, non-urgent communication.
      </Notice>

      <Notice title="In-app notifications">
        Header updates reflect live appointments, messages, and profile status for this clinic. A durable
        read/unread notification inbox is not exposed yet—events are queued in the server outbox for
        delivery plumbing, not as a patient notification API.
      </Notice>

      {/* Section A — Upcoming appointment */}
      <Section title="Upcoming appointment" actions={<Link className="button button-light button-small" href="/patient/appointments">All appointments</Link>}>
        {!scheduling ? (
          <Notice title="Online booking isn’t available yet" tone="warning">
            Contact {tenant_name} directly to schedule a visit.
          </Notice>
        ) : (
          <QueryView state={appointments.state} onRetry={appointments.reload} rows={2} loadingLabel="Loading appointments">
            {() =>
              next ? (
                <Card className="upcoming-appointment-card">
                  <ul className="appointment-list appointment-feature">
                    <AppointmentItem
                      appointment={next}
                      showDate
                      actions={
                        <div className="row-actions">
                          <Link className="button button-small button-light" href="/patient/appointments">
                            View
                          </Link>
                          <Link className="button button-small button-light" href="/patient/appointments">
                            Reschedule
                          </Link>
                          <Link className="button button-small button-light" href="/patient/appointments">
                            Cancel
                          </Link>
                        </div>
                      }
                    />
                  </ul>
                  <dl className="upcoming-meta">
                    <div>
                      <dt>Clinic</dt>
                      <dd>{tenant_name}</dd>
                    </div>
                    <div>
                      <dt>Type</dt>
                      <dd>Visit</dd>
                    </div>
                    <div>
                      <dt>Time zone</dt>
                      <dd>{timeZoneLabel(next.timezone, new Date(next.starts_at))}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>
                        <StatusBadge status={next.status} />
                      </dd>
                    </div>
                  </dl>
                </Card>
              ) : (
                <EmptyState
                  title="No upcoming appointments"
                  action={
                    <Link className="button button-small" href="/patient/care">
                      Book appointment
                    </Link>
                  }
                >
                  Book with a verified provider at {tenant_name}.
                </EmptyState>
              )
            }
          </QueryView>
        )}
      </Section>

      {/* Section B — Quick actions */}
      <Section title="Quick actions">
        <div className="action-grid">
          {scheduling ? (
            <Link className="action-card" href="/patient/care">
              <strong>Book appointment</strong>
              <span>Choose a verified provider and available time.</span>
            </Link>
          ) : null}
          <Link className="action-card" href="/patient/records">
            <strong>View medical records</strong>
            <span>Browse documents connected to this clinic.</span>
          </Link>
          <Link className="action-card" href="/patient/records">
            <strong>Upload medical document</strong>
            <span>Add a lab report or visit summary securely.</span>
          </Link>
          <Link className="action-card" href="/patient/messages">
            <strong>View messages</strong>
            <span>Open authorized clinic conversations.</span>
          </Link>
          <Link className="action-card" href="/patient/timeline">
            <strong>View care activities</strong>
            <span>Follow your Health Timeline and follow-ups.</span>
          </Link>
        </div>
      </Section>

      <DashboardGrid className="patient-dashboard-main">
        {/* Section C — Recent medical records */}
        <Section
          title="Recent medical records"
          actions={<Link className="button button-light button-small" href="/patient/records">All records</Link>}
        >
          <SearchField
            label="Search your documents"
            value={recordQuery}
            onChange={setRecordQuery}
            placeholder="Search documents…"
          />
          <QueryView state={documents.state} onRetry={documents.reload} rows={3} loadingLabel="Loading records">
            {() =>
              recentDocs.length ? (
                <ul className="dashboard-list" style={{ marginTop: 12 }}>
                  {recentDocs.map((doc) => (
                    <li key={doc.document_id}>
                      <div>
                        <strong>{doc.original_filename}</strong>
                        <span className="muted">
                          {doc.content_type} · {formatDate(doc.created_at)} · {tenant_name}
                        </span>
                      </div>
                      <div className="row-actions">
                        <StatusBadge status={doc.lifecycle_state} />
                        <Link className="button button-small button-light" href="/patient/records">
                          View
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  title={recordQuery ? "No matching documents" : "No documents yet"}
                  action={
                    <Link className="button button-small" href="/patient/records">
                      Upload document
                    </Link>
                  }
                >
                  Lab reports and visit summaries appear here after you upload them.
                </EmptyState>
              )
            }
          </QueryView>
        </Section>

        {/* Section D — Messages */}
        <Section title="Messages" actions={<Link className="button button-light button-small" href="/patient/messages">Open inbox</Link>}>
          <SearchField
            label="Search conversations"
            value={messageQuery}
            onChange={setMessageQuery}
            placeholder="Search conversations…"
          />
          <QueryView state={threads.state} onRetry={threads.reload} rows={3} loadingLabel="Loading messages">
            {() =>
              recentThreads.length ? (
                <ul className="dashboard-list" style={{ marginTop: 12 }}>
                  {recentThreads.map((thread) => (
                    <li key={thread.thread_id}>
                      <div>
                        <strong>{thread.subject || "Care conversation"}</strong>
                        <span className="muted">
                          {tenant_name} · {thread.message_count} message
                          {thread.message_count === 1 ? "" : "s"} · {formatDate(thread.updated_at)}
                        </span>
                      </div>
                      <div className="row-actions">
                        <StatusBadge status={thread.status} />
                        <Link className="button button-small button-light" href="/patient/messages">
                          Open
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  title={messageQuery ? "No matching conversations" : "No open messages"}
                  action={
                    <Link className="button button-small" href="/patient/messages">
                      Start a message
                    </Link>
                  }
                >
                  Secure clinic conversations appear here. Previews stay limited to subject and counts.
                </EmptyState>
              )
            }
          </QueryView>
        </Section>
      </DashboardGrid>

      {/* Section E — Care activities */}
      <Section title="Care activities" description="Administrative and scheduling tasks supported by this clinic portal.">
        <ul className="dashboard-list">
          {careActivities.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <span className="muted">{item.detail}</span>
              </div>
              <Link className="button button-small button-light" href={item.href}>
                Open
              </Link>
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Activity timeline"
        description="Appointments, documents, and visits from authorized clinic events."
        actions={
          <Link className="button button-light button-small" href="/patient/timeline">
            Full timeline
          </Link>
        }
      >
        <HealthTimeline path={`/api/v1/tenants/${tenant_id}/patients/me/timeline`} base="patient" />
      </Section>

      <p className="privacy-note">
        Your clinic connections are separate. A clinic can&apos;t see another clinic&apos;s records unless you
        explicitly allow it.
      </p>
    </>
  );
}
