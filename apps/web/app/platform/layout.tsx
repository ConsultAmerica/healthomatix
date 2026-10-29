import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { BrandMark } from "@/app/brand-mark";
import { ThemeToggle } from "@/components/theme-provider";
import { ToastProvider } from "@/components/ui";
import "../portal.css";

export const metadata: Metadata = {
  title: "Platform operations | Healthomatix",
  description: "Hypercare, customer success, and SaaS operations.",
};

const NAV = [
  { label: "Command center", href: "/platform" },
  { label: "Incidents", href: "/platform/incidents" },
  { label: "Customers", href: "/platform/customers" },
  { label: "Revenue", href: "/platform/revenue" },
  { label: "AI command", href: "/platform/ai" },
  { label: "AI readiness", href: "/platform/ai/readiness" },
  { label: "AI capabilities", href: "/platform/ai/capabilities" },
  { label: "Compliance", href: "/platform/compliance" },
  { label: "Automations", href: "/platform/automations" },
];

export default function PlatformLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <div className="portal-shell">
        <aside className="portal-nav">
          <div className="portal-brand">
            <BrandMark />
            <span>PLATFORM</span>
          </div>
          <nav>
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="portal-nav-link">
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="portal-nav-footer">
            <Link href="/clinic">Clinic workspace</Link>
            <ThemeToggle />
          </div>
        </aside>
        <main className="portal-main">{children}</main>
      </div>
    </ToastProvider>
  );
}
