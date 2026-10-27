"use client";

import Link from "next/link";
import { AppointmentItem } from "@/components/appointments";
import { useActiveMembership, usePortal } from "@/components/portal/portal-context";
import { EmptyState, Notice, PageHeader, QueryView, Section, StatTile } from "@/components/ui";
import { api, call, callOptional, useApiQuery } from "@/lib/api";
import { isFuture } from "@/lib/time";

export default function PatientHomePage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const { features } = usePortal();
  const scheduling = features?.schedulingEnabled ?? false;
  const path = { params: { path: { tenant_id } } };

  const appointments = useApiQuery(scheduling ? `my-appointments:${tenant_id}` : null, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/appointments", path)),
  );
  const documents = useApiQuery(`documents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/documents", path)),
  );
  const consents = useApiQuery(`consents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/consents", path)),
  );
  const profile = useApiQuery(`patient-profile:${tenant_id}`, () =>
    callOptional(api().GET("/api/v1/tenants/{tenant_id}/patients/me", path), "PROFILE_NOT_FOUND"));

  const upcoming =
    appointments.state.status === "success"
      ? appointments.state.data
          .filter((item) => item.status === "booked" && isFuture(item.starts_at))
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      : [];
  const activeConsents =
    consents.state.status === "success"
      ? consents.state.data.filter(
          (grant) => !grant.withdrawn_at && (!grant.expires_at || isFuture(grant.expires_at)),
        ).length
      : "—";
  const name = profile.state.status === "success" ? profile.state.data?.preferred_name : "";

  return (
    <>
      <PageHeader
        eyebrow={tenant_name.toUpperCase()}
        title={name ? `Welcome back, ${name}` : "Welcome back"}
        description="Here's what's happening with your care."
        actions={
          scheduling && (
            <Link className="button button-small" href="/patient/care">
              Book an appointment
            </Link>
          )
        }
      />

      {profile.state.status === "success" && !profile.state.data && (
        <Notice title="Finish setting up your profile">
          Tell your clinic what to call you and how to reach you. <Link href="/patient/profile">Complete profile</Link>
        </Notice>
      )}

      <div className="stat-grid">
        <StatTile
          label="Upcoming appointments"
          value={scheduling ? (appointments.state.status === "success" ? upcoming.length : "—") : "Off"}
          href="/patient/appointments"
        />
        <StatTile
          label="Documents"
          value={documents.state.status === "success" ? documents.state.data.length : "—"}
          href="/patient/records"
        />
        <StatTile label="Active consents" value={activeConsents} href="/patient/profile" />
      </div>

      <Section title="Your next appointment">
        {!scheduling ? (
          <Notice title="Online booking isn't available yet" tone="warning">
            Your clinic hasn&apos;t turned on online scheduling. Contact the clinic directly to book.
          </Notice>
        ) : (
          <QueryView state={appointments.state} onRetry={appointments.reload} rows={1}>
            {() =>
              upcoming[0] ? (
                <ul className="appointment-list appointment-feature">
                  <AppointmentItem
                    appointment={upcoming[0]}
                    showDate
                    actions={
                      <Link className="button button-light button-small" href="/patient/appointments">
                        Manage
                      </Link>
                    }
                  />
                </ul>
              ) : (
                <EmptyState
                  title="No upcoming appointments"
                  action={
                    <Link className="button button-small" href="/patient/care">
                      Find a time
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

      <p className="privacy-note">
        Your clinic connections are separate. A clinic can&apos;t see another clinic&apos;s records unless you
        explicitly allow it.
      </p>
    </>
  );
}
