import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import type { NextRequest, NextResponse } from "next/server";
import { demoSettings } from "./demo";
import { oidcSettings, refreshTokens, type TokenSet } from "./oidc";

export const SESSION_COOKIE = "hx_session";
export const LOGIN_COOKIE = "hx_oidc_login";

// Browsers reject cookies over ~4KB; leave headroom for name and attributes.
const MAX_COOKIE_BYTES = 3800;
const REFRESH_SKEW_MS = 60_000;
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 12;

export type BrowserSession = {
  accessToken: string;
  refreshToken?: string;
  expiresAt: number;
  createdAt: number;
  /** Set for demo-mode sessions; no identity-provider token exists. */
  demoUser?: string;
};

export function demoSession(personaId: string): BrowserSession {
  const now = Date.now();
  return {
    accessToken: "",
    expiresAt: now + SESSION_MAX_AGE_SECONDS * 1000,
    createdAt: now,
    demoUser: personaId,
  };
}

export type LoginState = {
  state: string;
  codeVerifier: string;
  returnTo: string;
};

function sessionKey(): Buffer | null {
  const secret = process.env.SESSION_SECRET ?? "";
  if (secret.length < 32) {
    return null;
  }
  return createHash("sha256").update(secret).digest();
}

export function sessionSecretConfigured(): boolean {
  return sessionKey() !== null;
}

export function seal(value: unknown): string {
  const key = sessionKey();
  if (!key) {
    throw new Error("SESSION_SECRET must be at least 32 characters.");
  }
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]).toString("base64url");
}

export function unseal<T>(sealed: string | undefined): T | null {
  const key = sessionKey();
  if (!key || !sealed) {
    return null;
  }
  try {
    const raw = Buffer.from(sealed, "base64url");
    const decipher = createDecipheriv("aes-256-gcm", key, raw.subarray(0, 12));
    decipher.setAuthTag(raw.subarray(12, 28));
    const plaintext = Buffer.concat([decipher.update(raw.subarray(28)), decipher.final()]);
    return JSON.parse(plaintext.toString("utf8")) as T;
  } catch {
    return null;
  }
}

function secureCookies(): boolean {
  return (process.env.APP_BASE_URL ?? "").startsWith("https://") || process.env.NODE_ENV === "production";
}

export function sessionFromTokens(tokens: TokenSet, previous?: BrowserSession): BrowserSession {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? previous?.refreshToken,
    expiresAt: Date.now() + Math.max(30, tokens.expires_in ?? 300) * 1000,
    createdAt: previous?.createdAt ?? Date.now(),
  };
}

export function writeSession(response: NextResponse, session: BrowserSession): boolean {
  let sealed = seal(session);
  if (sealed.length > MAX_COOKIE_BYTES && session.refreshToken) {
    // Keep sign-in working with oversized refresh tokens; the session simply ends at expiry.
    sealed = seal({ ...session, refreshToken: undefined });
  }
  if (sealed.length > MAX_COOKIE_BYTES) {
    return false;
  }
  response.cookies.set(SESSION_COOKIE, sealed, {
    httpOnly: true,
    secure: secureCookies(),
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
  return true;
}

export function clearSession(response: NextResponse): void {
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: secureCookies(), sameSite: "lax", path: "/", maxAge: 0 });
}

export function writeLoginState(response: NextResponse, login: LoginState): void {
  response.cookies.set(LOGIN_COOKIE, seal(login), {
    httpOnly: true,
    secure: secureCookies(),
    sameSite: "lax",
    path: "/auth",
    maxAge: 600,
  });
}

export function clearLoginState(response: NextResponse): void {
  response.cookies.set(LOGIN_COOKIE, "", { httpOnly: true, secure: secureCookies(), sameSite: "lax", path: "/auth", maxAge: 0 });
}

export function readSession(request: NextRequest): BrowserSession | null {
  const session = unseal<BrowserSession>(request.cookies.get(SESSION_COOKIE)?.value);
  if (!session || Date.now() - session.createdAt > SESSION_MAX_AGE_SECONDS * 1000) {
    return null;
  }
  return session;
}

export type ActiveSession =
  | { status: "active"; session: BrowserSession; refreshed: boolean }
  | { status: "expired" }
  | { status: "none" };

/** Returns a session with a usable access token, refreshing it when it is about to expire. */
export async function resolveSession(request: NextRequest): Promise<ActiveSession> {
  const session = readSession(request);
  if (!session) {
    return { status: "none" };
  }
  if (session.demoUser) {
    // Demo sessions stop working as soon as demo mode is switched off.
    return demoSettings() && session.expiresAt > Date.now()
      ? { status: "active", session, refreshed: false }
      : { status: "none" };
  }
  if (session.expiresAt - Date.now() > REFRESH_SKEW_MS) {
    return { status: "active", session, refreshed: false };
  }
  const settings = oidcSettings();
  if (!session.refreshToken || !settings) {
    return session.expiresAt > Date.now() ? { status: "active", session, refreshed: false } : { status: "expired" };
  }
  try {
    const tokens = await refreshTokens(settings, session.refreshToken);
    return { status: "active", session: sessionFromTokens(tokens, session), refreshed: true };
  } catch {
    return { status: "expired" };
  }
}

function configuredOrigin(): string | null {
  try {
    return process.env.APP_BASE_URL ? new URL(process.env.APP_BASE_URL).origin : null;
  } catch {
    return null;
  }
}

/**
 * The origin the browser used. `request.nextUrl` is normalized by the server
 * (for example to localhost), so prefer APP_BASE_URL, then the Host header.
 */
export function requestOrigin(request: NextRequest): string {
  const configured = configuredOrigin();
  if (configured) {
    return configured;
  }
  const host = request.headers.get("host");
  return host ? `${request.nextUrl.protocol}//${host}` : request.nextUrl.origin;
}

export function appUrl(request: NextRequest, path: string): URL {
  return new URL(path, requestOrigin(request));
}

/** Accepts state-changing requests only from this application's own origin. */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  return origin !== null && origin === requestOrigin(request);
}

export function safeReturnTo(value: string | null): string {
  if (value && /^\/(clinic|patient)(\/[A-Za-z0-9/_-]*)?$/.test(value)) {
    return value;
  }
  return "/patient";
}
