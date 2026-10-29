"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { TrendsPanel } from "@/components/trends/trends-panel";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader } from "@/components/ui";
import { apiJson } from "@/lib/fhir";
import type { ApiProblem } from "@/lib/api";

type SessionJoin = {
  session_id: string;
  status: string;
  video_provider: string;
  room_id: string;
  join_url: string;
  follow_up_plan?: string;
  encounter_id?: string | null;
};

export default function PatientVisitPage() {
  const params = useParams<{ sessionId: string }>();
  const { tenant_id } = useActiveMembership();
  const [join, setJoin] = useState<SessionJoin | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await apiJson<SessionJoin>(
        `/api/v1/tenants/${tenant_id}/sessions/${params.sessionId}/join`,
        { method: "POST", body: "{}" },
      );
      if (!result.ok) {
        setProblem(result.problem);
        return;
      }
      setJoin(result.data);
    })();
  }, [tenant_id, params.sessionId]);

  return (
    <>
      <PageHeader
        eyebrow="TELEHEALTH"
        title="Your video visit"
        description="Join your secure session. Clinical messages stay in the portal — never in email or SMS bodies."
      />
      {problem ? <FormError problem={problem} /> : null}
      {join ? (
        <>
          <section className="app-card" style={{ padding: 16, marginBottom: 16 }}>
            <h2 className="section-title">Session</h2>
            <p>
              Status <strong>{join.status}</strong> · {join.video_provider} room{" "}
              <code className="mono">{join.room_id}</code>
            </p>
            <Notice title="Privacy">
              Appointment reminders may use email or SMS, but they never include clinical details.
              Your visit and follow-up stay inside Healthomatix.
            </Notice>
            <p className="muted" style={{ wordBreak: "break-all", fontSize: "0.85rem" }}>
              {join.join_url}
            </p>
            {join.follow_up_plan ? (
              <div style={{ marginTop: 12 }}>
                <h3 className="section-title">Follow-up plan</h3>
                <p>{join.follow_up_plan}</p>
              </div>
            ) : null}
          </section>
          <TrendsPanel tenantId={tenant_id} title="Your trends" />
        </>
      ) : (
        !problem && <p className="muted">Joining…</p>
      )}
    </>
  );
}
