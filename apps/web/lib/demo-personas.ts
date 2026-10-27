/** Fixed synthetic test users for demo mode. Each maps to the API subject `demo-<id>`. */
export const DEMO_PERSONAS = [
  {
    id: "admin",
    label: "Clinic admin",
    portal: "clinic",
    hint: "Creates the clinic, invites the team, and reviews provider credentials.",
  },
  {
    id: "staff",
    label: "Clinic staff",
    portal: "clinic",
    hint: "Sees the patient roster and invites patients.",
  },
  {
    id: "provider",
    label: "Provider",
    portal: "clinic",
    hint: "Manages their profile, credentials, and availability.",
  },
  {
    id: "patient",
    label: "Patient",
    portal: "patient",
    hint: "Books appointments and manages profile and consent.",
  },
  {
    id: "patient-2",
    label: "Second patient",
    portal: "patient",
    hint: "A separate patient, useful for checking that records stay private.",
  },
] as const;

export type DemoPersona = (typeof DEMO_PERSONAS)[number];

export function findPersona(id: string | null | undefined): DemoPersona | undefined {
  return DEMO_PERSONAS.find((persona) => persona.id === id);
}
