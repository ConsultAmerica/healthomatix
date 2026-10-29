"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import type { PortalKind } from "./portal-context";

const STORAGE_KEY = "healthomatix-tour-dismissed";

type Step = {
  title: string;
  body: string;
  hint?: string;
  href?: string;
  hrefLabel?: string;
};

const STEPS: Step[] = [
  {
    title: "Welcome to the sandbox",
    body: "This is a synthetic walkthrough—no live PHI. Start by seeding the shared demo clinic so admin, provider, and patient personas share one tenant.",
    hint: "Use Seed sandbox in the demo bar, or Simulate Onboarding on the clinic readiness board, to move from unready to operational in one click.",
  },
  {
    title: "Health Timeline",
    body: "After seeding, open the patient Timeline to see verified glucose labs linked to a sample lab document—then switch to Provider to review the same chart.",
    href: "/patient/timeline",
    hrefLabel: "Open Health Timeline",
  },
  {
    title: "Clinic workspace",
    body: "Admins review readiness and credentials. Providers open the patient chart, trends, and consult sessions. Everything stays tenant-isolated.",
    href: "/clinic",
    hrefLabel: "Open clinic home",
  },
  {
    title: "Toggle between roles",
    body: "From the demo bar, switch Clinic admin → Provider → Patient without signing out. Passcode is only asked once per browser session.",
    hint: "Patient uploads, provider verifies extractions, then both see the timeline update.",
  },
  {
    title: "You’re ready",
    body: "Try upload → extract → verify → timeline → visit drafts. Restart this tour anytime from the demo bar.",
  },
];

export function SandboxTour({
  kind,
  open,
  onClose,
}: {
  kind: PortalKind;
  open: boolean;
  onClose: () => void;
}) {
  const titleId = useId();
  const [index, setIndex] = useState(0);
  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  useEffect(() => {
    if (open) setIndex(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const finish = useCallback(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    onClose();
  }, [onClose]);

  if (!open || !step) return null;

  return (
    <div className="sandbox-tour" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button className="sandbox-tour-backdrop" type="button" aria-label="Close tour" onClick={finish} />
      <div className="sandbox-tour-card">
        <div className="sandbox-tour-progress" aria-hidden="true">
          {STEPS.map((_, i) => (
            <span key={i} className={i <= index ? "is-active" : undefined} />
          ))}
        </div>
        <p className="sandbox-tour-kicker">
          2-minute tour · {kind === "clinic" ? "Clinic" : "Patient"} sandbox · Step {index + 1} of {STEPS.length}
        </p>
        <h2 id={titleId}>{step.title}</h2>
        <p>{step.body}</p>
        {step.hint && <p className="sandbox-tour-hint">{step.hint}</p>}
        {step.href && (
          <Link className="sandbox-tour-link" href={step.href} onClick={finish}>
            {step.hrefLabel ?? "Open"}
          </Link>
        )}
        <div className="sandbox-tour-actions">
          <button className="button button-light button-small" type="button" onClick={finish}>
            Skip
          </button>
          <div className="sandbox-tour-nav">
            {index > 0 && (
              <button className="button button-light button-small" type="button" onClick={() => setIndex((i) => i - 1)}>
                Back
              </button>
            )}
            {last ? (
              <button className="button button-small" type="button" onClick={finish}>
                Finish tour
              </button>
            ) : (
              <button className="button button-small" type="button" onClick={() => setIndex((i) => i + 1)}>
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function shouldAutoStartTour(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}
