import { NextResponse, type NextRequest } from "next/server";
import { discover, oidcSettings } from "@/lib/server/oidc";
import { appUrl, clearSession, isSameOrigin, readSession, safeReturnTo } from "@/lib/server/session";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json(
      { error: { code: "CSRF_REJECTED", message: "Sign-out must come from this site.", request_id: "" } },
      { status: 403 },
    );
  }

  let destination = appUrl(request, "/").toString();
  const settings = oidcSettings();
  if (readSession(request)?.demoUser) {
    // Demo users go back to the demo sign-in screen of the portal they were in.
    const form = await request.formData().catch(() => null);
    destination = appUrl(request, safeReturnTo(String(form?.get("returnTo") ?? ""))).toString();
  } else if (settings) {
    try {
      const { end_session_endpoint } = await discover(settings);
      if (end_session_endpoint?.startsWith("https://")) {
        const target = new URL(end_session_endpoint);
        target.searchParams.set("client_id", settings.clientId);
        target.searchParams.set("post_logout_redirect_uri", `${settings.appBaseUrl}/`);
        destination = target.toString();
      }
    } catch {
      // The local session is still cleared when the identity provider is unreachable.
    }
  }

  const response = NextResponse.redirect(destination, 303);
  clearSession(response);
  response.headers.set("Cache-Control", "no-store");
  return response;
}
