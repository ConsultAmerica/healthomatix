import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import { ThemeProvider, THEME_BOOT_SCRIPT } from "@/components/theme-provider";
import "./globals.css";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Healthomatix | Intelligent healthcare platform for modern clinics",
  description:
    "Manage appointments, patient records, online consultations, clinical documentation, and AI-powered healthcare workflows in one connected platform.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={outfit.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body suppressHydrationWarning>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
