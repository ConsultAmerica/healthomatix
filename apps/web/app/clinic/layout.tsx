import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PortalShell, type PortalConfig } from "@/components/portal/portal-shell";
import "../portal.css";

export const metadata: Metadata = {
  title: "Clinic workspace | Healthomatix",
  description: "Manage your clinic team, providers, patients, and schedule.",
};

const config: PortalConfig = {
  kind: "clinic",
  heading: "CLINIC WORKSPACE",
  nav: [
    { label: "Overview", href: "/clinic", icon: "home" },
    { label: "Schedule", href: "/clinic/schedule", icon: "calendar", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Patients", href: "/clinic/patients", icon: "users", roles: ["tenant_admin", "staff"] },
    { label: "Messages", href: "/clinic/messages", icon: "message", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Team", href: "/clinic/team", icon: "team", roles: ["tenant_admin"] },
    {
      label: "Providers",
      href: "/clinic/providers",
      icon: "badge",
      roles: ["tenant_admin", "provider"],
      labelFor: { provider: "My profile" },
    },
    { label: "Availability", href: "/clinic/availability", icon: "clock", roles: ["provider"] },
    { label: "Locations", href: "/clinic/locations", icon: "pin", roles: ["tenant_admin", "staff", "provider"] },
    { label: "Audit log", href: "/clinic/audit", icon: "log", roles: ["tenant_admin", "auditor"] },
  ],
  secondary: [
    { label: "Create another clinic", href: "/clinic/setup" },
    { label: "Join with an invitation", href: "/clinic/join" },
    { label: "Go to patient space", href: "/patient" },
  ],
  openPaths: ["/clinic/setup", "/clinic/join"],
};

export default function ClinicLayout({ children }: { children: ReactNode }) {
  return <PortalShell config={config}>{children}</PortalShell>;
}
