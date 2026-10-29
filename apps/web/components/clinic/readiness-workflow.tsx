"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/ui";

export type WorkflowStep = {
  id: string;
  label: string;
  detail: string;
  status: "complete" | "pending" | "blocked" | "review";
  href?: string;
};

/**
 * Visual approval / review strip for invites and credentials on the clinic home.
 */
export function ReadinessWorkflow({
  title,
  description,
  steps,
  actions,
}: {
  title: string;
  description?: string;
  steps: WorkflowStep[];
  actions?: ReactNode;
}) {
  return (
    <div className="readiness-workflow">
      <div className="readiness-workflow-head">
        <div>
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {actions ? <div className="readiness-workflow-actions">{actions}</div> : null}
      </div>
      <ol className="readiness-workflow-steps">
        {steps.map((step, index) => (
          <li key={step.id} className={`rw-step rw-${step.status}`}>
            <span className="rw-index" aria-hidden="true">
              {index + 1}
            </span>
            <div className="rw-body">
              <div className="rw-title-row">
                <strong>{step.label}</strong>
                <StatusBadge
                  tone={
                    step.status === "complete"
                      ? "success"
                      : step.status === "review"
                        ? "warning"
                        : step.status === "blocked"
                          ? "danger"
                          : "info"
                  }
                >
                  {step.status === "complete"
                    ? "Done"
                    : step.status === "review"
                      ? "Needs review"
                      : step.status === "blocked"
                        ? "Blocked"
                        : "Pending"}
                </StatusBadge>
              </div>
              <p>{step.detail}</p>
              {step.href && (
                <Link className="rw-link" href={step.href}>
                  Open
                </Link>
              )}
            </div>
            {index < steps.length - 1 && <span className="rw-connector" aria-hidden="true" />}
          </li>
        ))}
      </ol>
    </div>
  );
}
