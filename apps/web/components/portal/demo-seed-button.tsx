"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiJson } from "@/lib/fhir";
import { usePortal } from "./portal-context";
import { useToast } from "@/components/ui";

type SeedResult = {
  tenant_id: string;
  tenant_name: string;
  created: boolean;
  clinic_patient_id: string;
};

/**
 * One-click provision of the shared demo sandbox clinic for DEMO_AUTH personas.
 */
export function DemoSeedButton({
  label = "Seed demo clinic",
  redirectTo,
  className = "button",
}: {
  label?: string;
  redirectTo?: string;
  className?: string;
}) {
  const { demo, refresh, selectTenant } = usePortal();
  const notify = useToast();
  const router = useRouter();
  const [pending, setPending] = useState(false);

  if (!demo.enabled) return null;

  async function seed() {
    setPending(true);
    const result = await apiJson<SeedResult>("/api/v1/demo/seed", { method: "POST", body: "{}" });
    setPending(false);
    if (!result.ok) {
      notify(result.problem.message, "danger");
      return;
    }
    selectTenant(result.data.tenant_id);
    refresh();
    notify(
      result.data.created
        ? `${result.data.tenant_name} is ready — switch personas from the demo bar.`
        : `${result.data.tenant_name} is already linked. Opening workspace.`,
    );
    router.push(redirectTo ?? "/clinic");
  }

  return (
    <button className={className} type="button" onClick={seed} disabled={pending} aria-busy={pending}>
      {pending ? "Seeding…" : label}
    </button>
  );
}
