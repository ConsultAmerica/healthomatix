"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppointmentDays } from "@/components/appointments";
import { ClinicalWorkboard } from "@/components/clinic/clinical-workboard";
import { InviteDialog } from "@/components/clinic/invite-dialog";
import { ReadinessWorkflow, type WorkflowStep } from "@/components/clinic/readiness-workflow";
import { SimulateOnboarding } from "@/components/clinic/simulate-onboarding";
import { ROLE_LABELS, useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView, Section, StatTile, StatusBadge } from "@/components/ui";
import { api, call, useApiQuery } from "@/lib/api";
import { addDays, formatDateTime, isFuture } from "@/lib/time";

function count<T>(state: { status: string; data?: T[] }) {
  return state.status === "success" && state.data ? state.data.length : "—";
}

export default function ClinicOverviewPage() {
  const membership = useActiveMembership();
  const { features, demo } = usePortal();
  const tenant_id = membership.tenant_id;
  const role = membership.role;
  const isAdmin = role === "tenant_admin";
  const isProvider = role === "provider";
  const canSeeSchedule = ["tenant_admin", "staff", "provider"].includes(role);
  const scheduling = features?.schedulingEnabled ?? false;
  const [inviteOpen, setInviteOpen] = useState(false);
  const [todayLabel, setTodayLabel] = useState("TODAY");
  const path = { params: { path: { tenant_id } } };

  useEffect(() => {
    setTodayLabel(
      new Intl.DateTimeFormat("en-US", { weekday: "long", day: "numeric", month: "long" })
        .format(new Date())
        .toUpperCase(),
    );
  }, []);

  const members = useApiQuery(isAdmin ? `members:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/members", path)),
  );
  const invitations = useApiQuery(isAdmin ? `invitations:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/invitations", path)),
  );
  const patients = useApiQuery(isAdmin || role === "staff" ? `patients:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients", path)),
  );
  const threads = useApiQuery(
    ["tenant_admin", "staff", "provider"].includes(role) ? `clinic-threads-home:${tenant_id}` : null,
    () => call(api().GET("/api/v1/tenants/{tenant_id}/threads", path)),
  );
  const credentials = useApiQuery(isAdmin ? `credential-queue:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/provider-credentials", path)),
  );
  const ownCredentials = useApiQuery(isProvider ? `own-credentials:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/providers/me/credentials", path)),
  );
  const upcoming = useApiQuery(canSeeSchedule && scheduling ? `upcoming:${tenant_id}` : null, () => {
    const from = new Date();
    return call(
      api().GET("/api/v1/tenants/{tenant_id}/appointments", {
        params: { path: { tenant_id }, query: { from: from.toISOString(), to: addDays(from, 7).toISOString() } },
      }),
    );
  });
  const audit = useApiQuery(role === "auditor" ? `audit-preview:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/audit-events", { params: { path: { tenant_id }, query: { limit: 8 } } })),
  );

  const pendingInviteCount =
    invitations.state.status === "success"
      ? invitations.state.data.filter((invite) => invite.status === "pending" && isFuture(invite.expires_at)).length
      : 0;
  const pendingInvites = invitations.state.status === "success" ? pendingInviteCount : "—";
  const credentialsToReview =
    credentials.state.status === "success" ? credentials.state.data.length : 0;
  const latestCredential = ownCredentials.state.status === "success" ? ownCredentials.state.data[0] : undefined;

  const adminWorkflow: WorkflowStep[] = [
    {
      id: "invite",
      label: "Membership invites",
      detail:
        pendingInviteCount > 0
          ? `${pendingInviteCount} invitation code${pendingInviteCount === 1 ? "" : "s"} awaiting acceptance.`
          : "No open invites — create codes when you add staff, providers, or patients.",
      status: pendingInviteCount > 0 ? "pending" : "complete",
      href: "/clinic/team",
    },
    {
      id: "credential",
      label: "Credential review",
      detail:
        credentialsToReview > 0
          ? `${credentialsToReview} provider credential${credentialsToReview === 1 ? "" : "s"} waiting for clinic verification.`
          : "Review queue is clear. Providers cannot self-verify.",
      status: credentialsToReview > 0 ? "review" : "complete",
      href: "/clinic/providers",
    },
    {
      id: "schedule",
      label: "Scheduling gate",
      detail: scheduling
        ? "Scheduling is enabled — verified providers can publish availability."
        : "Scheduling is off in this environment; booking stays unavailable.",
      status: scheduling ? "complete" : "blocked",
      href: "/clinic/schedule",
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow={todayLabel}
        title={`${membership.tenant_name}`}
        description={`Clinic dashboard · signed in as ${ROLE_LABELS[role] ?? role}. Appointments, patients, and tasks for your role.`}
        actions={
          (isAdmin || role === "staff") && (
            <button className="button button-small" type="button" onClick={() => setInviteOpen(true)}>
              {isAdmin ? "Invite someone" : "Invite a patient"}
            </button>
          )
        }
      />

      {isAdmin && (
        <div className="stat-grid">
          <StatTile label="Team members" icon="team" value={count(members.state)} href="/clinic/team" />
          <StatTile label="Pending invitations" icon="mail" value={pendingInvites} hint="Codes not yet used" href="/clinic/team" />
          <StatTile label="Patients" icon="users" value={count(patients.state)} hint="Connected to this clinic" href="/clinic/patients" />
          <StatTile
            label="Open messages"
            icon="message"
            value={
              threads.state.status === "success"
                ? threads.state.data.filter((thread) => thread.status === "open").length
                : "—"
            }
            href="/clinic/messages"
          />
          <StatTile
            label="Credentials to review"
            icon="badge"
            attention={credentials.state.status === "success" && credentials.state.data.length > 0}
            value={count(credentials.state)}
            hint="Providers awaiting verification"
            href="/clinic/providers"
          />
        </div>
      )}

      {isAdmin && (
        <Section
          title="Approval workflow"
          description="Pending invites and credential reviews, shown as the path from invite → verify → book."
        >
          <ReadinessWorkflow
            title="Clinic readiness board"
            description="Live status of the same gates that block actions until membership and credentials clear. Use Simulate Onboarding to walk unready → operational in the demo sandbox."
            steps={adminWorkflow}
            actions={
              demo.enabled ? (
                <SimulateOnboarding
                  onComplete={() => {
                    members.reload();
                    invitations.reload();
                    credentials.reload();
                    patients.reload();
                  }}
                />
              ) : null
            }
          />
        </Section>
      )}

      {role === "staff" && (
        <div className="stat-grid">
          <StatTile label="Patients" icon="users" value={count(patients.state)} href="/clinic/patients" />
          <StatTile label="Appointments next 7 days" icon="calendar" value={scheduling ? count(upcoming.state) : "Off"} href="/clinic/schedule" />
          <StatTile
            label="Open messages"
            icon="message"
            value={
              threads.state.status === "success"
                ? threads.state.data.filter((thread) => thread.status === "open").length
                : "—"
            }
            href="/clinic/messages"
          />
        </div>
      )}

      {isProvider ? (
        <Notice title="Doctor workspace">
          Your focused clinical board lives at{" "}
          <Link href="/clinic/doctor">Clinical board</Link>
          {" · "}
          <Link href="/clinic/consultations">Consultations</Link>
          {" · "}
          <Link href="/clinic/patients">Patient charts</Link>. Admin tools (team, locations, audit)
          stay with clinic administrators.
        </Notice>
      ) : null}

      {(isProvider || role === "staff" || isAdmin) && (
        <Section
          title="Clinical workboard"
          description="What needs attention now—today’s visits, waiting patients, lab verification, and AI drafts awaiting your approval."
        >
          <ClinicalWorkboard tenantId={tenant_id} />
        </Section>
      )}

      {isProvider && (
        <Section title="Your readiness" description="Patients can only book providers with an active profile and a verified credential.">
          <QueryView state={ownCredentials.state} onRetry={ownCredentials.reload} rows={1}>
            {() =>
              latestCredential ? (
                <div className="readiness-row">
                  <div>
                    <p className="readiness-row-title">
                      {latestCredential.credential_type.replaceAll("_", " ")} · {latestCredential.jurisdiction}
                    </p>
                    <p className="readiness-row-meta">Submitted {formatDateTime(latestCredential.submitted_at)}</p>
                  </div>
                  <StatusBadge status={latestCredential.status} />
                </div>
              ) : (
                <EmptyState
                  title="No credential submitted yet"
                  action={
                    <Link className="button button-small" href="/clinic/providers">
                      Complete your profile
                    </Link>
                  }
                >
                  Add your professional credential so a clinic administrator can verify it.
                </EmptyState>
              )
            }
          </QueryView>
        </Section>
      )}

      {canSeeSchedule && !isProvider && (
        <Section
          title="Next 7 days"
          description="Booked appointments across the clinic."
          actions={
            <Link className="button button-light button-small" href="/clinic/schedule">
              Open schedule
            </Link>
          }
        >
          {!scheduling ? (
            <Notice title="Scheduling is turned off" tone="warning">
              Online booking hasn&apos;t been enabled for this environment, so no appointments are shown.
            </Notice>
          ) : (
            <QueryView state={upcoming.state} onRetry={upcoming.reload}>
              {(appointments) =>
                appointments.length ? (
                  <AppointmentDays appointments={appointments} showPatient />
                ) : (
                  <EmptyState title="Nothing booked this week">New bookings will appear here as patients schedule.</EmptyState>
                )
              }
            </QueryView>
          )}
        </Section>
      )}

      {role === "auditor" && (
        <Section
          title="Recent activity"
          actions={
            <Link className="button button-light button-small" href="/clinic/audit">
              Full audit log
            </Link>
          }
        >
          <QueryView state={audit.state} onRetry={audit.reload}>
            {(events) =>
              events.length ? (
                <ul className="activity-list">
                  {events.map((event) => (
                    <li key={event.event_id}>
                      <span>{event.action.replaceAll("_", " ").replaceAll(".", " · ")}</span>
                      <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No activity yet" />
              )
            }
          </QueryView>
        </Section>
      )}

      {isAdmin && (
        <Section title="Quick actions">
          <div className="action-grid">
            <button className="action-card" type="button" onClick={() => setInviteOpen(true)}>
              <strong>Invite your team</strong>
              <span>Add staff and providers with single-use codes.</span>
            </button>
            <Link className="action-card" href="/clinic/providers">
              <strong>Review credentials</strong>
              <span>Verify providers before they can offer appointments.</span>
            </Link>
            <Link className="action-card" href="/clinic/locations">
              <strong>Manage locations</strong>
              <span>Set where and in which time zone care happens.</span>
            </Link>
          </div>
        </Section>
      )}

      <p className="privacy-note">
        A clinic role alone never grants access to a patient&apos;s chart. Care relationships and explicit
        authorization are required.
      </p>

      <InviteDialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onCreated={() => {
          invitations.reload();
        }}
        defaultRole={isAdmin ? "staff" : "patient"}
      />
    </>
  );
}
