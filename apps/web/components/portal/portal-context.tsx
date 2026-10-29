"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, call, type ApiProblem, type Membership, type UserAccount } from "@/lib/api";

export type PortalKind = "clinic" | "patient";
export type Role = "tenant_admin" | "staff" | "provider" | "auditor" | "patient";

export const ROLE_LABELS: Record<string, string> = {
  tenant_admin: "Clinic admin",
  staff: "Clinic staff",
  provider: "Doctor",
  auditor: "Auditor",
  patient: "Patient",
};

const PORTAL_ROLES: Record<PortalKind, string[]> = {
  clinic: ["tenant_admin", "staff", "provider", "auditor"],
  patient: ["patient"],
};

export type Features = {
  oidcConfigured: boolean;
  schedulingEnabled: boolean;
  documentStorageConfigured: boolean;
};

export type DemoInfo = { enabled: boolean; passcodeRequired: boolean; user: string | null };

type SessionStatus = {
  sign_in_configured: boolean;
  authenticated: boolean;
  expired: boolean;
  demo_enabled?: boolean;
  demo_passcode_required?: boolean;
  demo_user?: string | null;
};

export type PortalState =
  | { status: "loading" }
  | { status: "signed-out"; signInConfigured: boolean; expired: boolean }
  | { status: "error"; problem: ApiProblem }
  | { status: "ready"; user: UserAccount };

type PortalContextValue = {
  kind: PortalKind;
  state: PortalState;
  features: Features | null;
  demo: DemoInfo;
  memberships: Membership[];
  active: Membership | null;
  selectTenant: (tenantId: string) => void;
  refresh: () => void;
};

const PortalContext = createContext<PortalContextValue | null>(null);

function storageKey(kind: PortalKind) {
  return `healthomatix.activeTenant.${kind}`;
}

function readStoredTenant(kind: PortalKind): string | null {
  try {
    return window.localStorage.getItem(storageKey(kind));
  } catch {
    return null;
  }
}

export function PortalProvider({ kind, children }: { kind: PortalKind; children: ReactNode }) {
  const [state, setState] = useState<PortalState>({ status: "loading" });
  const [features, setFeatures] = useState<Features | null>(null);
  const [demo, setDemo] = useState<DemoInfo>({ enabled: false, passcodeRequired: false, user: null });
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    setSelectedTenant(readStoredTenant(kind));
  }, [kind]);

  useEffect(() => {
    let active = true;
    call(api().GET("/api/v1/auth/config")).then((result) => {
      if (active && result.ok) {
        const config = result.data as {
          oidc_configured?: boolean;
          scheduling_enabled?: boolean;
          document_storage_configured?: boolean;
        };
        setFeatures({
          oidcConfigured: Boolean(config.oidc_configured),
          schedulingEnabled: Boolean(config.scheduling_enabled),
          documentStorageConfigured: Boolean(config.document_storage_configured),
        });
      }
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      let session: SessionStatus;
      try {
        const response = await fetch("/api/session", { cache: "no-store" });
        session = await response.json();
      } catch {
        if (active) {
          setState({
            status: "error",
            problem: {
              kind: "unavailable",
              status: 0,
              code: "NETWORK_ERROR",
              message: "Your session could not be checked. Try again shortly.",
              requestId: "",
              fields: {},
            },
          });
        }
        return;
      }
      if (active) {
        setDemo({
          enabled: Boolean(session.demo_enabled),
          passcodeRequired: Boolean(session.demo_passcode_required),
          user: session.demo_user ?? null,
        });
      }
      if (!session.authenticated) {
        if (active) {
          setState({ status: "signed-out", signInConfigured: session.sign_in_configured, expired: session.expired });
        }
        return;
      }
      const me = await call(api().GET("/api/v1/me"));
      if (!active) return;
      if (me.ok) {
        setState({ status: "ready", user: me.data });
      } else if (me.problem.kind === "unauthenticated") {
        setState({ status: "signed-out", signInConfigured: session.sign_in_configured, expired: true });
      } else {
        setState({ status: "error", problem: me.problem });
      }
    })();
    return () => {
      active = false;
    };
  }, [version]);

  const memberships = useMemo(
    () =>
      state.status === "ready"
        ? state.user.memberships.filter(
            (membership) => membership.status === "active" && PORTAL_ROLES[kind].includes(membership.role),
          )
        : [],
    [state, kind],
  );

  const active = useMemo(
    () => memberships.find((membership) => membership.tenant_id === selectedTenant) ?? memberships[0] ?? null,
    [memberships, selectedTenant],
  );

  const selectTenant = useCallback(
    (tenantId: string) => {
      setSelectedTenant(tenantId);
      try {
        window.localStorage.setItem(storageKey(kind), tenantId);
      } catch {
        // Selection still applies for this page view.
      }
    },
    [kind],
  );

  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  const value = useMemo(
    () => ({ kind, state, features, demo, memberships, active, selectTenant, refresh }),
    [kind, state, features, demo, memberships, active, selectTenant, refresh],
  );

  return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>;
}

export function usePortal() {
  const context = useContext(PortalContext);
  if (!context) {
    throw new Error("usePortal must be used inside a PortalProvider.");
  }
  return context;
}

/** The selected clinic membership. Only call inside pages rendered by PortalShell with a membership. */
export function useActiveMembership(): Membership {
  const { active } = usePortal();
  if (!active) {
    throw new Error("No active clinic membership.");
  }
  return active;
}
