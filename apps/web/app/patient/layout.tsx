import type { Metadata } from "next";
import type { ReactNode } from "react";
import { PortalShell, type PortalConfig } from "@/components/portal/portal-shell";
import "../portal.css";

export const metadata: Metadata = {
  title: "Patient space | Healthomatix",
  description: "Your appointments, records, and consent choices with your clinic.",
};

const config: PortalConfig = {
  kind: "patient",
  heading: "YOUR SPACE",
  nav: [
    { label: "Home", href: "/patient", icon: "home" },
    { label: "Book care", href: "/patient/care", icon: "plus" },
    { label: "Appointments", href: "/patient/appointments", icon: "calendar" },
    { label: "Records", href: "/patient/records", icon: "file" },
    { label: "Messages", href: "/patient/messages", icon: "message" },
    { label: "Profile & consent", href: "/patient/profile", icon: "shield" },
  ],
  secondary: [
    { label: "Connect another clinic", href: "/patient/join" },
    { label: "Go to clinic workspace", href: "/clinic" },
  ],
  openPaths: ["/patient/join"],
};

export default function PatientLayout({ children }: { children: ReactNode }) {
  return <PortalShell config={config}>{children}</PortalShell>;
}
