import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PortalShell, type PortalConfig } from "@/components/portal/portal-shell";
import "../portal.css";

export const metadata: Metadata = {
  title: "Patient dashboard | Healthomatix",
  description: "Your appointments, medical records, messages, and care options.",
};

const config: PortalConfig = {
  kind: "patient",
  heading: "PATIENT",
  nav: [
    { label: "Dashboard", href: "/patient", icon: "home" },
    { label: "Appointments", href: "/patient/appointments", icon: "calendar" },
    { label: "Medical Records", href: "/patient/records", icon: "file" },
    { label: "Messages", href: "/patient/messages", icon: "message" },
    { label: "Care", href: "/patient/care", icon: "stethoscope" },
    { label: "Profile", href: "/patient/profile", icon: "shield" },
  ],
  secondary: [
    { label: "Waiting room", href: "/patient/waiting-room" },
    { label: "Visit summary", href: "/patient/visit-summary" },
    { label: "Care activities", href: "/patient/care-tasks" },
    { label: "Education", href: "/patient/education" },
    { label: "Health Timeline", href: "/patient/timeline" },
    { label: "Health trends", href: "/patient/trends" },
    { label: "Data export", href: "/patient/export" },
    { label: "Connect another clinic", href: "/patient/join" },
    { label: "Go to clinic workspace", href: "/clinic" },
  ],
  openPaths: ["/patient/join"],
};

export default function PatientLayout({ children }: { children: ReactNode }) {
  return <PortalShell config={config}>{children}</PortalShell>;
}
