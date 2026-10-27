import { timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";
import { exchangeCode, oidcSettings } from "@/lib/server/oidc";
import {
  LOGIN_COOKIE,
  appUrl,
  clearLoginState,
  sessionFromTokens,
  unseal,
  writeSession,
  type LoginState,
} from "@/lib/server/session";

export const dynamic = "force-dynamic";

function sameValue(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function fail(request: NextRequest, returnTo: string, reason: string) {
  const response = NextResponse.redirect(appUrl(request, `${returnTo}?auth_error=${reason}`));
  clearLoginState(response);
  return response;
}

export async function GET(request: NextRequest) {
  const login = unseal<LoginState>(request.cookies.get(LOGIN_COOKIE)?.value);
  const returnTo = login?.returnTo ?? "/patient";
  const params = request.nextUrl.searchParams;
  const settings = oidcSettings();

  if (!settings) {
    return fail(request, returnTo, "sign_in_unavailable");
  }
  if (params.get("error")) {
    return fail(request, returnTo, params.get("error") === "access_denied" ? "access_denied" : "sign_in_failed");
  }
  const code = params.get("code");
  const state = params.get("state");
  if (!login || !code || !state || !sameValue(state, login.state)) {
    return fail(request, returnTo, "sign_in_expired");
  }

  try {
    const tokens = await exchangeCode(settings, code, login.codeVerifier);
    const response = NextResponse.redirect(appUrl(request, returnTo));
    clearLoginState(response);
    if (!writeSession(response, sessionFromTokens(tokens))) {
      return fail(request, returnTo, "session_too_large");
    }
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    return fail(request, returnTo, "sign_in_failed");
  }
}
