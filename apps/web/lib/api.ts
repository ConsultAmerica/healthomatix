"use client";

import { createHealthomatixClient, type HealthomatixSchemas } from "@healthomatix/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

export type Schemas = HealthomatixSchemas;
export type Membership = Schemas["MembershipRead"];
export type UserAccount = Schemas["UserRead"];

export type ProblemKind =
  | "unauthenticated"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "invalid"
  | "gone"
  | "unavailable"
  | "offline"
  | "unexpected";

export type ApiProblem = {
  kind: ProblemKind;
  status: number;
  code: string;
  message: string;
  requestId: string;
  fields: Record<string, string>;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; problem: ApiProblem };

let client: ReturnType<typeof createHealthomatixClient> | null = null;

/** Same-origin client; requests go through the session proxy, never directly to the API. */
export function api() {
  if (!client) {
    client = createHealthomatixClient(window.location.origin, undefined, {
      "x-healthomatix-csrf": "1",
    });
  }
  return client;
}

function kindFor(status: number): ProblemKind {
  if (status === 401) return "unauthenticated";
  if (status === 403) return "forbidden";
  if (status === 404) return "not-found";
  if (status === 409) return "conflict";
  if (status === 410) return "gone";
  if (status === 422) return "invalid";
  if (status === 502 || status === 503 || status === 504) return "unavailable";
  return "unexpected";
}

function problemFrom(status: number, body: unknown, requestId: string): ApiProblem {
  const fields: Record<string, string> = {};
  let code = `HTTP_${status}`;
  let message = "Something went wrong. Try again.";
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const error = record.error as Record<string, unknown> | undefined;
    if (error && typeof error === "object") {
      code = typeof error.code === "string" ? error.code : code;
      message = typeof error.message === "string" ? error.message : message;
      requestId = typeof error.request_id === "string" && error.request_id ? error.request_id : requestId;
    }
    if (Array.isArray(record.detail)) {
      code = "VALIDATION_FAILED";
      message = "Some details need attention.";
      for (const item of record.detail as Array<{ loc?: unknown[]; msg?: string }>) {
        const field = item.loc?.[item.loc.length - 1];
        if (typeof field === "string" && item.msg) {
          fields[field] = item.msg.replace(/^Value error, /, "");
        }
      }
    }
  }
  return { kind: kindFor(status), status, code, message, requestId, fields };
}

/** Normalizes an openapi-fetch call into a result with a classified problem. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<ApiResult<T>> {
  try {
    const { data, error, response } = await request;
    if (response.ok) {
      return { ok: true, data: data as T };
    }
    return {
      ok: false,
      problem: problemFrom(response.status, error, response.headers.get("x-request-id") ?? ""),
    };
  } catch {
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    return {
      ok: false,
      problem: {
        kind: offline ? "offline" : "unavailable",
        status: 0,
        code: offline ? "OFFLINE" : "NETWORK_ERROR",
        message: offline
          ? "You appear to be offline. Reconnect and try again."
          : "The service could not be reached. Try again shortly.",
        requestId: "",
        fields: {},
      },
    };
  }
}

/** Like `call`, but treats the given not-found code as an expected empty result (`null`). */
export async function callOptional<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
  missingCode: string,
): Promise<ApiResult<T | null>> {
  const result = await call(request);
  if (!result.ok && result.problem.code === missingCode) {
    return { ok: true, data: null };
  }
  return result;
}

export type QueryState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T; refreshing: boolean }
  | { status: "error"; problem: ApiProblem };

/**
 * Loads data when `key` changes. Pass a null key to skip loading (for example,
 * when no clinic is selected yet). Previous data stays visible while reloading.
 */
export function useApiQuery<T>(key: string | null, load: () => Promise<ApiResult<T>>) {
  const [state, setState] = useState<QueryState<T>>(key ? { status: "loading" } : { status: "idle" });
  const [version, setVersion] = useState(0);
  const loader = useRef(load);
  loader.current = load;

  useEffect(() => {
    if (!key) {
      setState({ status: "idle" });
      return;
    }
    let active = true;
    setState((previous) =>
      previous.status === "success" ? { ...previous, refreshing: true } : { status: "loading" },
    );
    loader.current().then((result) => {
      if (!active) return;
      setState(
        result.ok
          ? { status: "success", data: result.data, refreshing: false }
          : { status: "error", problem: result.problem },
      );
    });
    return () => {
      active = false;
    };
  }, [key, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { state, reload };
}

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
