import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PortalShell, type PortalConfig } from "@/components/portal/portal-shell";
import "../portal.css";

export const metadata: Metadata = {
  title: "Clinic dashboard | Healthomatix",
  description: "Manage patients, appointments, providers, team, and clinic operations.",
};

const config: PortalConfig = {
  kind: "clinic",
  heading: "CLINIC",
  nav: [
    {
      label: "Dashboard",
      href: "/clinic",
      icon: "home",
      roles: ["tenant_admin", "staff", "auditor"],
    },
    {
      label: "Dashboard",
      href: "/clinic/doctor",
      icon: "home",
      roles: ["provider"],
    },
    {
      label: "Patients",
      href: "/clinic/patients",
      icon: "users",
      roles: ["tenant_admin", "staff", "provider"],
    },
    {
      label: "Appointments",
      href: "/clinic/schedule",
      icon: "calendar",
      roles: ["tenant_admin", "staff", "provider"],
    },
    {
      label: "Providers",
      href: "/clinic/providers",
      icon: "badge",
      roles: ["tenant_admin", "provider"],
      labelFor: { provider: "My credentials" },
    },
    { label: "Team", href: "/clinic/team", icon: "team", roles: ["tenant_admin"] },
    {
      label: "Locations",
      href: "/clinic/locations",
      icon: "pin",
      roles: ["tenant_admin", "staff"],
    },
    { label: "Audit", href: "/clinic/audit", icon: "log", roles: ["tenant_admin", "auditor"] },
  ],
  secondary: [
    { label: "Clinical board", href: "/clinic/doctor", roles: ["tenant_admin", "staff"] },
    { label: "Consultations", href: "/clinic/consultations", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Telehealth ops", href: "/clinic/telehealth", roles: ["tenant_admin", "staff", "provider"] },
    { label: "AI scribe", href: "/clinic/ai-scribe", roles: ["tenant_admin", "staff", "provider"] },
    { label: "AI approvals", href: "/clinic/ai-approvals", roles: ["tenant_admin", "staff", "provider"] },
    { label: "AI clinical context", href: "/clinic/ai-context", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Workflow analytics", href: "/clinic/analytics", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Insurance", href: "/clinic/insurance", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Revenue cycle", href: "/clinic/rcm", roles: ["tenant_admin", "staff"] },
    { label: "Integrations", href: "/clinic/integrations", roles: ["tenant_admin", "staff"] },
    { label: "Support", href: "/clinic/support", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Onboarding", href: "/clinic/onboarding", roles: ["tenant_admin", "staff"] },
    { label: "Subscription", href: "/clinic/subscription", roles: ["tenant_admin"] },
    { label: "Messages", href: "/clinic/messages", roles: ["tenant_admin", "staff", "provider"] },
    { label: "My availability", href: "/clinic/availability", roles: ["provider"] },
    { label: "Create another clinic", href: "/clinic/setup" },
    { label: "Join with an invitation", href: "/clinic/join" },
    { label: "Go to patient space", href: "/patient" },
  ],
  openPaths: ["/clinic/setup", "/clinic/join"],
};

export default function ClinicLayout({ children }: { children: ReactNode }) {
  return <PortalShell config={config}>{children}</PortalShell>;
}
