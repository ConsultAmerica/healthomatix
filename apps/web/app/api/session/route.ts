import { NextResponse, type NextRequest } from "next/server";
import { oidcSettings } from "@/lib/server/oidc";
import { clearSession, resolveSession, writeSession } from "@/lib/server/session";

export const dynamic = "force-dynamic";

/** Reports sign-in state to the browser without ever exposing tokens. */
export async function GET(request: NextRequest) {
  const signInConfigured = oidcSettings() !== null;
  const resolved = await resolveSession(request);
  const response = NextResponse.json(
    {
      sign_in_configured: signInConfigured,
      authenticated: resolved.status === "active",
      expired: resolved.status === "expired",
    },
    { headers: { "Cache-Control": "no-store" } },
  );
  if (resolved.status === "active" && resolved.refreshed) {
    writeSession(response, resolved.session);
  } else if (resolved.status === "expired") {
    clearSession(response);
  }
  return response;
}
