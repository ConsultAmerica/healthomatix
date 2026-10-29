"use client";

import { HealthTimeline } from "@/components/timeline/health-timeline";
import { useActiveMembership } from "@/components/portal/portal-context";
import { Notice, PageHeader, Section } from "@/components/ui";

export default function PatientTimelinePage() {
  const { tenant_id } = useActiveMembership();

  return (
    <>
      <PageHeader
        eyebrow="HEALTH TIMELINE"
        title="Your care story"
        description="Verified labs, uploaded documents, visits, and appointments in one chronological view. AI-extracted values appear only after clinician verification."
      />
      <Notice title="Synthetic demo data" tone="info">
        Timeline entries are consent-scoped and never invent chart access. Seed the demo clinic to see sample glucose
        results linked to a lab document.
      </Notice>
      <Section title="Timeline">
        <HealthTimeline path={`/api/v1/tenants/${tenant_id}/patients/me/timeline`} base="patient" />
      </Section>
    </>
  );
}
