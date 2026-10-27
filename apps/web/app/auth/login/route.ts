import { NextResponse, type NextRequest } from "next/server";
import { callbackUrl, discover, oidcSettings, pkceChallenge, randomToken } from "@/lib/server/oidc";
import { appUrl, safeReturnTo, writeLoginState } from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  const settings = oidcSettings();
  if (!settings) {
    return NextResponse.redirect(appUrl(request, `${returnTo}?auth_error=sign_in_unavailable`));
  }

  let authorizationEndpoint: string;
  try {
    authorizationEndpoint = (await discover(settings)).authorization_endpoint;
  } catch {
    return NextResponse.redirect(appUrl(request, `${returnTo}?auth_error=identity_unreachable`));
  }

  const state = randomToken();
  const codeVerifier = randomToken();
  const target = new URL(authorizationEndpoint);
  target.search = new URLSearchParams({
    response_type: "code",
    client_id: settings.clientId,
    redirect_uri: callbackUrl(settings),
    scope: settings.scopes,
    state,
    code_challenge: pkceChallenge(codeVerifier),
    code_challenge_method: "S256",
    ...(settings.audience ? { audience: settings.audience } : {}),
  }).toString();

  const response = NextResponse.redirect(target);
  writeLoginState(response, { state, codeVerifier, returnTo });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
