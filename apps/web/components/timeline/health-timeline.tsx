"use client";

import Link from "next/link";
import { EmptyState, LoadingState, ProblemState, StatusBadge } from "@/components/ui";
import { apiJson } from "@/lib/fhir";
import { formatDateTime } from "@/lib/time";
import { useCallback, useEffect, useState } from "react";
import type { ApiProblem } from "@/lib/api";

export type TimelineEvent = {
  event_id: string;
  kind: string;
  title: string;
  summary: string;
  status: string;
  occurred_at: string;
  resource_type: string;
  resource_id: string;
  source_document_id: string | null;
  href_hint: string;
};

type TimelinePayload = {
  patient_user_id: string;
  events: TimelineEvent[];
};

const KIND_LABEL: Record<string, string> = {
  observation: "Lab",
  document: "Document",
  encounter: "Visit",
  appointment: "Appointment",
  session: "Session",
};

function hrefFor(event: TimelineEvent, base: "patient" | "clinic", clinicPatientId?: string): string | null {
  if (base === "patient") {
    if (event.href_hint === "trends") return "/patient/trends";
    if (event.href_hint === "records") return "/patient/records";
    if (event.href_hint === "appointments") return "/patient/appointments";
    return null;
  }
  if (!clinicPatientId) return null;
  if (event.href_hint === "trends" || event.kind === "observation") {
    return `/clinic/patients/${clinicPatientId}`;
  }
  if (event.href_hint === "records" || event.kind === "document") {
    return `/clinic/patients/${clinicPatientId}`;
  }
  return `/clinic/patients/${clinicPatientId}`;
}

export function HealthTimeline({
  path,
  base,
  clinicPatientId,
}: {
  path: string;
  base: "patient" | "clinic";
  clinicPatientId?: string;
}) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setProblem(null);
    const result = await apiJson<TimelinePayload>(path);
    setLoading(false);
    if (!result.ok) {
      setProblem(result.problem);
      setEvents(null);
      return;
    }
    setEvents(result.data.events);
  }, [path]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !events) {
    return <LoadingState label="Loading health timeline" rows={5} />;
  }
  if (problem) {
    return <ProblemState problem={problem} onRetry={load} />;
  }
  if (!events?.length) {
    return (
      <EmptyState title="No timeline events yet">
        Verified labs, uploaded documents, visits, and appointments will appear here in chronological order.
      </EmptyState>
    );
  }

  return (
    <ol className="health-timeline">
      {events.map((event) => {
        const href = hrefFor(event, base, clinicPatientId);
        const body = (
          <>
            <div className="health-timeline-meta">
              <span className={`health-timeline-kind kind-${event.kind}`}>
                {KIND_LABEL[event.kind] ?? event.kind}
              </span>
              <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
              <StatusBadge status={event.status} />
            </div>
            <strong className="health-timeline-title">{event.title}</strong>
            <p className="health-timeline-summary">{event.summary}</p>
            {event.source_document_id && (
              <p className="health-timeline-source">
                Source document · <code>{event.source_document_id.slice(0, 12)}…</code>
              </p>
            )}
          </>
        );
        return (
          <li key={event.event_id} className={`health-timeline-item kind-${event.kind}`}>
            <span className="health-timeline-rail" aria-hidden="true" />
            {href ? (
              <Link className="health-timeline-card" href={href}>
                {body}
              </Link>
            ) : (
              <div className="health-timeline-card">{body}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
