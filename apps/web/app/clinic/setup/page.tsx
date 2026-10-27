"use client";

import { CreateClinicForm } from "@/components/portal/onboarding";
import { PageHeader } from "@/components/ui";

export default function ClinicSetupPage() {
  return (
    <>
      <PageHeader
        eyebrow="CLINIC SETUP"
        title="Create a clinic"
        description="Set up a separate clinic workspace. You'll be its administrator, and its records stay separate from any other clinic."
      />
      <div className="app-card narrow-card">
        <CreateClinicForm />
      </div>
    </>
  );
}
