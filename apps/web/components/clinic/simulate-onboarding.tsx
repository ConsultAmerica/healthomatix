"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiJson } from "@/lib/fhir";
import { usePortal } from "@/components/portal/portal-context";
import { useToast } from "@/components/ui";

type SeedResult = {
  tenant_id: string;
  tenant_name: string;
  created: boolean;
  clinic_patient_id: string;
};

type SimStep = {
  id: string;
  label: string;
  detail: string;
};

const SIM_STEPS: SimStep[] = [
  {
    id: "unready",
    label: "Clinic unready",
    detail: "No shared sandbox tenant yet—invites unused, credentials pending, scheduling gated.",
  },
  {
    id: "seed",
    label: "Seed sandbox tenant",
    detail: "Provision the demo clinic and link admin, provider, staff, and patient personas.",
  },
  {
    id: "credentials",
    label: "Verify provider credential",
    detail: "Clear the credential review queue so patients can book a verified provider.",
  },
  {
    id: "invites",
    label: "Activate memberships",
    detail: "Join demo personas to the tenant so unused invitation codes are no longer blocking readiness.",
  },
  {
    id: "operational",
    label: "Fully operational",
    detail: "Scheduling, chart consent, sample labs, and workboard data are ready to explore.",
  },
];

/**
 * One-click guided walkthrough: unready → seeded/operational for the demo sandbox.
 * Seeds when DEMO_AUTH is on; still animates the transition for education.
 */
export function SimulateOnboarding({
  onComplete,
  className = "button button-small",
}: {
  onComplete?: () => void;
  className?: string;
}) {
  const { demo, refresh, selectTenant } = usePortal();
  const notify = useToast();
  const router = useRouter();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  function close() {
    clearTimers();
    setOpen(false);
    setRunning(false);
    setActiveIndex(0);
    setDone(false);
    setError(null);
  }

  async function run() {
    setOpen(true);
    setRunning(true);
    setDone(false);
    setError(null);
    setActiveIndex(0);
    clearTimers();

    const advance = (index: number, delay: number) =>
      new Promise<void>((resolve) => {
        const id = window.setTimeout(() => {
          setActiveIndex(index);
          resolve();
        }, delay);
        timers.current.push(id);
      });

    try {
      await advance(0, 400);
      await advance(1, 700);

      if (demo.enabled) {
        const result = await apiJson<SeedResult>("/api/v1/demo/seed", { method: "POST", body: "{}" });
        if (!result.ok) {
          setError(result.problem.message);
          setRunning(false);
          return;
        }
        selectTenant(result.data.tenant_id);
        notify(
          result.data.created
            ? `${result.data.tenant_name} seeded — finishing readiness walkthrough.`
            : `${result.data.tenant_name} already linked — showing operational path.`,
        );
      }

      await advance(2, 900);
      await advance(3, 900);
      await advance(4, 800);
      setDone(true);
      setRunning(false);
      refresh();
      onComplete?.();
    } catch {
      setError("The onboarding simulation could not finish. Try again shortly.");
      setRunning(false);
    }
  }

  if (!demo.enabled) {
    return (
      <p className="simulate-onboarding-hint muted">
        Simulate Onboarding is available when demo auth is enabled for this environment.
      </p>
    );
  }

  return (
    <div className="simulate-onboarding">
      <button className={className} type="button" onClick={() => void run()} disabled={running}>
        {running ? "Simulating…" : "Simulate Onboarding"}
      </button>
      <p className="simulate-onboarding-caption muted">
        One click walks the readiness board from unready → seeded → operational using the synthetic demo clinic.
      </p>

      {open ? (
        <div className="simulate-onboarding-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
          <button className="simulate-onboarding-backdrop" type="button" aria-label="Close" onClick={close} />
          <div className="simulate-onboarding-card">
            <p className="section-kicker">Guided sandbox seeding</p>
            <h2 id={titleId}>Simulate clinic onboarding</h2>
            <p className="muted">
              Watch the state transition from pending invites and credentials to a fully operational demo tenant.
              Synthetic data only—no live PHI.
            </p>

            <ol className="simulate-onboarding-steps">
              {SIM_STEPS.map((step, index) => {
                const state =
                  index < activeIndex ? "complete" : index === activeIndex ? (done && index === SIM_STEPS.length - 1 ? "complete" : "active") : "pending";
                return (
                  <li key={step.id} className={`sim-step sim-${state}`}>
                    <span className="sim-index" aria-hidden="true">
                      {state === "complete" ? "✓" : index + 1}
                    </span>
                    <div>
                      <strong>{step.label}</strong>
                      <span>{step.detail}</span>
                    </div>
                  </li>
                );
              })}
            </ol>

            {error ? <p className="form-error">{error}</p> : null}

            <div className="simulate-onboarding-actions">
              <button className="button button-light button-small" type="button" onClick={close}>
                {done ? "Close" : "Cancel"}
              </button>
              {done ? (
                <button
                  className="button button-small"
                  type="button"
                  onClick={() => {
                    close();
                    router.push("/clinic");
                  }}
                >
                  Open clinic dashboard
                </button>
              ) : (
                <button className="button button-small" type="button" disabled={running} onClick={() => void run()}>
                  {running ? "Working…" : "Retry"}
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
