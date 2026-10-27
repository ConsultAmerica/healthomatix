"use client";

import { JoinClinicForm } from "@/components/portal/onboarding";
import { PageHeader } from "@/components/ui";

export default function ClinicJoinPage() {
  return (
    <>
      <PageHeader
        eyebrow="JOIN A CLINIC"
        title="Join with an invitation"
        description="Enter the single-use code a clinic administrator shared with you. Your role is set by the invitation."
      />
      <div className="app-card narrow-card">
        <JoinClinicForm />
      </div>
    </>
  );
}
