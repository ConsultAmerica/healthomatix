"use client";

import { useActiveMembership } from "@/components/portal/portal-context";
import { EmptyState, PageHeader } from "@/components/ui";

export default function MessagesPage() {
  const { tenant_name } = useActiveMembership();
  return (
    <>
      <PageHeader eyebrow="MESSAGES" title="Secure messages" />
      <EmptyState title="Secure messaging is coming soon">
        You&apos;ll be able to message your care team at {tenant_name} here. For now, please contact the clinic
        directly. In an emergency, call your local emergency number.
      </EmptyState>
    </>
  );
}
