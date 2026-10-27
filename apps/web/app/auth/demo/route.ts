import { NextResponse, type NextRequest } from "next/server";
import { findPersona } from "@/lib/demo-personas";
import { demoSettings, passcodeMatches } from "@/lib/server/demo";
import { appUrl, demoSession, isSameOrigin, readSession, writeSession } from "@/lib/server/session";

export const dynamic = "force-dynamic";

/** Starts or switches a demo-mode session from the sign-in form or the demo banner. */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json(
      { error: { code: "CSRF_REJECTED", message: "Demo sign-in must come from this site.", request_id: "" } },
      { status: 403 },
    );
  }

  const form = await request.formData();
  const persona = findPersona(String(form.get("persona") ?? ""));
  const returnTo = String(form.get("returnTo") ?? "");
  const fallback = `/${persona?.portal ?? "clinic"}`;
  const settings = demoSettings();

  if (!settings) {
    return NextResponse.redirect(appUrl(request, `${fallback}?auth_error=demo_unavailable`), 303);
  }
  if (!persona) {
    return NextResponse.redirect(appUrl(request, `${fallback}?auth_error=demo_failed`), 303);
  }
  // Switching between demo users doesn't ask for the passcode again.
  const alreadyDemo = Boolean(readSession(request)?.demoUser);
  if (!alreadyDemo && !passcodeMatches(settings, String(form.get("passcode") ?? ""))) {
    return NextResponse.redirect(appUrl(request, `${fallback}?auth_error=demo_passcode`), 303);
  }

  // Land in the portal that matches the chosen role.
  const destination = returnTo.startsWith(`/${persona.portal}`) ? returnTo : `/${persona.portal}`;
  const response = NextResponse.redirect(appUrl(request, destination), 303);
  writeSession(response, demoSession(persona.id));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
