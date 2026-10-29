/** Shared synthetic consent scopes for landing payload demos (not live PHI). */

export type ConsentScopeDef = {
  id: string;
  label: string;
  detail: string;
  resources: string[];
  /** Schemas whose sample payload is trimmed when this scope is off. */
  affects: string[];
};

export const CONSENT_SCOPES: ConsentScopeDef[] = [
  {
    id: "visit_summary",
    label: "Visit summaries",
    detail: "Encounter notes and follow-up plans shared with the care team.",
    resources: ["Visit notes", "Encounters", "Medical Records"],
    affects: ["ConsentRead", "DocumentRead", "PatientProfileRead"],
  },
  {
    id: "lab_history",
    label: "Lab histories",
    detail: "Lab values and reports—restricted until this scope is on.",
    resources: ["Lab Results", "Diagnostic Reports"],
    affects: ["ConsentRead", "DocumentRead"],
  },
  {
    id: "schedule",
    label: "Schedule & reminders",
    detail: "Appointments and contact channels for booking changes.",
    resources: ["Appointments", "Contact details"],
    affects: ["ConsentRead", "AppointmentRead", "AvailabilityRead", "PatientProfileRead"],
  },
  {
    id: "meds",
    label: "Medication list",
    detail: "Planned pharmacy edge—shown here to illustrate payload trimming.",
    resources: ["Medications (planned)"],
    affects: ["ConsentRead", "PatientProfileRead"],
  },
];

export const DEFAULT_CONSENT_ENABLED: Record<string, boolean> = {
  visit_summary: true,
  lab_history: false,
  schedule: true,
  meds: false,
};

export function activeScopeIds(enabled: Record<string, boolean>): string[] {
  return CONSENT_SCOPES.filter((scope) => enabled[scope.id]).map((scope) => scope.id);
}

export function schemaAffectedByConsent(schemaName: string): boolean {
  return CONSENT_SCOPES.some((scope) => scope.affects.includes(schemaName));
}
