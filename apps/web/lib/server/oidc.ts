import "server-only";

import { createHash, randomBytes } from "node:crypto";

export type OidcSettings = {
  issuer: string;
  clientId: string;
  clientSecret: string;
  audience: string;
  scopes: string;
  appBaseUrl: string;
};

export type TokenSet = {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  refresh_token?: string;
};

type Discovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
};

let discoveryCache: { issuer: string; value: Discovery; fetchedAt: number } | null = null;

/** Returns browser sign-in settings, or null when this deployment is not configured for sign-in. */
export function oidcSettings(): OidcSettings | null {
  const issuer = (process.env.OIDC_ISSUER ?? "").trim().replace(/\/$/, "");
  const clientId = (process.env.OIDC_CLIENT_ID ?? "").trim();
  const appBaseUrl = (process.env.APP_BASE_URL ?? "").trim().replace(/\/$/, "");
  const secret = process.env.SESSION_SECRET ?? "";
  if (!issuer.startsWith("https://") || !clientId || !appBaseUrl || secret.length < 32) {
    return null;
  }
  return {
    issuer,
    clientId,
    clientSecret: (process.env.OIDC_CLIENT_SECRET ?? "").trim(),
    audience: (process.env.OIDC_AUDIENCE ?? "").trim(),
    scopes: (process.env.OIDC_SCOPES ?? "openid profile offline_access").trim(),
    appBaseUrl,
  };
}

export async function discover(settings: OidcSettings): Promise<Discovery> {
  if (
    discoveryCache &&
    discoveryCache.issuer === settings.issuer &&
    Date.now() - discoveryCache.fetchedAt < 60 * 60 * 1000
  ) {
    return discoveryCache.value;
  }
  const response = await fetch(`${settings.issuer}/.well-known/openid-configuration`, {
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    throw new Error(`OIDC discovery failed with HTTP ${response.status}.`);
  }
  const value = (await response.json()) as Discovery;
  if (value.issuer.replace(/\/$/, "") !== settings.issuer) {
    throw new Error("OIDC discovery issuer does not match OIDC_ISSUER.");
  }
  for (const endpoint of [value.authorization_endpoint, value.token_endpoint]) {
    if (!endpoint?.startsWith("https://")) {
      throw new Error("OIDC endpoints must use HTTPS.");
    }
  }
  discoveryCache = { issuer: settings.issuer, value, fetchedAt: Date.now() };
  return value;
}

export function randomToken(): string {
  return randomBytes(32).toString("base64url");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function callbackUrl(settings: OidcSettings): string {
  return `${settings.appBaseUrl}/auth/callback`;
}

async function tokenRequest(settings: OidcSettings, body: URLSearchParams): Promise<TokenSet> {
  const { token_endpoint } = await discover(settings);
  body.set("client_id", settings.clientId);
  if (settings.clientSecret) {
    body.set("client_secret", settings.clientSecret);
  }
  const response = await fetch(token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    throw new Error(`Token request failed with HTTP ${response.status}.`);
  }
  const tokens = (await response.json()) as TokenSet;
  if (typeof tokens.access_token !== "string" || !tokens.access_token) {
    throw new Error("Token response did not include an access token.");
  }
  return tokens;
}

export function exchangeCode(settings: OidcSettings, code: string, codeVerifier: string) {
  return tokenRequest(
    settings,
    new URLSearchParams({
      grant_type: "authorization_code",
      code,
      code_verifier: codeVerifier,
      redirect_uri: callbackUrl(settings),
    }),
  );
}

export function refreshTokens(settings: OidcSettings, refreshToken: string) {
  return tokenRequest(
    settings,
    new URLSearchParams({ grant_type: "refresh_token", refresh_token: refreshToken }),
  );
}
