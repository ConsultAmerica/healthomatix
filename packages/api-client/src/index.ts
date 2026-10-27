import createClient from "openapi-fetch";
import type { components, paths } from "./generated/schema";

export type HealthomatixApiPaths = paths;
export type HealthomatixSchemas = components["schemas"];

export function createHealthomatixClient(
  baseUrl: string,
  accessToken?: string,
  headers?: Record<string, string>,
) {
  return createClient<paths>({
    baseUrl,
    headers: {
      ...headers,
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });
}
