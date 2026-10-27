"use client";

import { JoinClinicForm } from "@/components/portal/onboarding";
import { PageHeader } from "@/components/ui";

export default function PatientJoinPage() {
  return (
    <>
      <PageHeader
        eyebrow="CONNECT A CLINIC"
        title="Connect another clinic"
        description="Enter the invitation code your clinic gave you. Each clinic connection is separate, and records aren't shared between clinics."
      />
      <div className="app-card narrow-card">
        <JoinClinicForm />
      </div>
    </>
  );
}
