"use client";

import { TrendsPanel } from "@/components/trends/trends-panel";
import { useActiveMembership } from "@/components/portal/portal-context";
import { PageHeader } from "@/components/ui";

export default function PatientTrendsPage() {
  const { tenant_id } = useActiveMembership();

  return (
    <>
      <PageHeader
        eyebrow="YOUR RESULTS"
        title="Health trends"
        description="Verified lab results over time, with reference ranges and educational change notes."
      />
      <TrendsPanel tenantId={tenant_id} />
    </>
  );
}
