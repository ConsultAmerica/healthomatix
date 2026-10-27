import "server-only";

import { timingSafeEqual } from "node:crypto";

export type DemoSettings = { secret: string; passcode: string };

/**
 * Demo sign-in for synthetic testing. Enabled only when DEMO_AUTH_SECRET is set;
 * the API must hold the same secret, and refuses it in production.
 */
export function demoSettings(): DemoSettings | null {
  const secret = (process.env.DEMO_AUTH_SECRET ?? "").trim();
  if (secret.length < 32) {
    return null;
  }
  return { secret, passcode: (process.env.DEMO_PASSCODE ?? "").trim() };
}

export function passcodeMatches(settings: DemoSettings, supplied: string): boolean {
  if (!settings.passcode) {
    return true;
  }
  const expected = Buffer.from(settings.passcode);
  const actual = Buffer.from(supplied);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}
