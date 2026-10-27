import { NextResponse, type NextRequest } from "next/server";
import { demoSettings } from "@/lib/server/demo";
import { clearSession, isSameOrigin, resolveSession, writeSession } from "@/lib/server/session";

export const dynamic = "force-dynamic";

type ProxyContext = { params: Promise<{ path: string[] }> };

const CSRF_HEADER = "x-healthomatix-csrf";
const PUBLIC_PATHS = new Set(["health", "auth/config"]);

function problem(status: number, code: string, message: string) {
  return NextResponse.json(
    { error: { code, message, request_id: "" } },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

function apiBaseUrl(): string | null {
  const value = (process.env.HEALTHOMATIX_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "").trim();
  return value ? value.replace(/\/$/, "") : null;
}

/**
 * Same-origin proxy to the Healthomatix API. The access token stays in the
 * encrypted, httpOnly session cookie and is attached here, server-side.
 */
async function proxy(request: NextRequest, context: ProxyContext) {
  const { path } = await context.params;
  const joined = path.join("/");

  // Platform administration is a separate, restricted surface.
  if (path[0] === "platform") {
    return problem(404, "NOT_FOUND", "Not found.");
  }
  const mutating = !["GET", "HEAD"].includes(request.method);
  if (mutating && (!isSameOrigin(request) || request.headers.get(CSRF_HEADER) !== "1")) {
    return problem(403, "CSRF_REJECTED", "This request could not be verified. Reload the page and try again.");
  }
  const base = apiBaseUrl();
  if (!base) {
    return problem(503, "API_NOT_CONFIGURED", "The Healthomatix API address is not configured for this site.");
  }

  const resolved = await resolveSession(request);
  if (resolved.status !== "active" && !PUBLIC_PATHS.has(joined)) {
    const response = problem(
      401,
      resolved.status === "expired" ? "SESSION_EXPIRED" : "AUTH_REQUIRED",
      resolved.status === "expired" ? "Your session has ended. Sign in again to continue." : "Sign in to continue.",
    );
    if (resolved.status === "expired") {
      clearSession(response);
    }
    return response;
  }

  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  if (resolved.status === "active") {
    const demo = resolved.session.demoUser ? demoSettings() : null;
    if (demo) {
      headers.set("X-Demo-User", `demo-${resolved.session.demoUser}`);
      headers.set("X-Demo-Secret", demo.secret);
    } else {
      headers.set("Authorization", `Bearer ${resolved.session.accessToken}`);
    }
  }

  const target = `${base}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: mutating ? await request.text() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    return problem(502, "API_UNREACHABLE", "The Healthomatix API could not be reached. Try again shortly.");
  }

  const body = upstream.status === 204 ? null : await upstream.arrayBuffer();
  const response = new NextResponse(body, { status: upstream.status });
  response.headers.set("Cache-Control", "no-store");
  for (const name of ["content-type", "x-request-id"]) {
    const value = upstream.headers.get(name);
    if (value) {
      response.headers.set(name, value);
    }
  }
  if (resolved.status === "active" && resolved.refreshed) {
    writeSession(response, resolved.session);
  }
  return response;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
