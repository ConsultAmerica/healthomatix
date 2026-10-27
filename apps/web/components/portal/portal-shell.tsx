"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { BrandMark } from "@/app/brand-mark";
import { LoadingState, ProblemState, ToastProvider } from "@/components/ui";
import { NoMembership, SignInPanel } from "./onboarding";
import { PortalProvider, ROLE_LABELS, usePortal, type PortalKind, type Role } from "./portal-context";

export type NavItem = {
  label: string;
  href: string;
  roles?: Role[];
  /** Label override per role, for items whose meaning differs by role. */
  labelFor?: Partial<Record<Role, string>>;
};

export type PortalConfig = {
  kind: PortalKind;
  heading: string;
  nav: NavItem[];
  secondary: NavItem[];
  /** Routes that work before the user belongs to any clinic. */
  openPaths: string[];
};

export function PortalShell({ config, children }: { config: PortalConfig; children: ReactNode }) {
  return (
    <PortalProvider kind={config.kind}>
      <ToastProvider>
        <ShellFrame config={config}>{children}</ShellFrame>
      </ToastProvider>
    </PortalProvider>
  );
}

function isCurrent(pathname: string, href: string, root: string) {
  return href === root ? pathname === root : pathname === href || pathname.startsWith(`${href}/`);
}

function ShellFrame({ config, children }: { config: PortalConfig; children: ReactNode }) {
  const pathname = usePathname();
  const { state, memberships, active, selectTenant, refresh } = usePortal();
  const [authError, setAuthError] = useState<string | null>(null);
  const root = `/${config.kind}`;
  const role = active?.role as Role | undefined;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("auth_error");
    if (error) {
      setAuthError(error);
      params.delete("auth_error");
      const query = params.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    }
  }, []);

  const visibleNav = config.nav.filter((item) => !item.roles || (role && item.roles.includes(role)));
  const ready = state.status === "ready";

  let content: ReactNode;
  if (state.status === "loading") {
    content = <LoadingState label="Checking your session" rows={4} />;
  } else if (state.status === "signed-out") {
    content = (
      <SignInPanel
        kind={config.kind}
        configured={state.signInConfigured}
        expired={state.expired}
        authError={authError}
        returnTo={pathname}
      />
    );
  } else if (state.status === "error") {
    content = <ProblemState problem={state.problem} onRetry={refresh} />;
  } else if (!active && !config.openPaths.includes(pathname)) {
    content = <NoMembership kind={config.kind} />;
  } else {
    // Re-mount pages when the clinic changes so no data from the previous clinic lingers.
    content = <div key={active?.tenant_id ?? "none"}>{children}</div>;
  }

  return (
    <div className={`portal-shell ${config.kind}-shell app-shell`}>
      <a className="skip-link" href="#app-main">
        Skip to content
      </a>
      <header className="topbar">
        <Link className="wordmark" href="/" aria-label="Healthomatix home">
          <BrandMark />
        </Link>
        <div className="topbar-actions">
          {ready && memberships.length > 1 && active && (
            <label className="tenant-switcher">
              <span className="visually-hidden">Current clinic</span>
              <select value={active.tenant_id} onChange={(event) => selectTenant(event.target.value)}>
                {memberships.map((membership) => (
                  <option key={membership.tenant_id} value={membership.tenant_id}>
                    {membership.tenant_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {ready && memberships.length === 1 && active && <span className="tenant-name">{active.tenant_name}</span>}
          {role && <span className="role-pill">{ROLE_LABELS[role]?.toUpperCase() ?? role}</span>}
          {ready ? (
            <form method="post" action="/auth/logout">
              <button className="topbar-home topbar-button" type="submit">
                Sign out
              </button>
            </form>
          ) : (
            <Link className="topbar-home" href="/">
              Home
            </Link>
          )}
        </div>
      </header>
      <div className="portal-layout">
        <nav className="side-nav" aria-label={`${config.heading} navigation`}>
          <p className="nav-heading">{config.heading}</p>
          {ready && active
            ? visibleNav.map((item) => {
                const current = isCurrent(pathname, item.href, root);
                return (
                  <Link
                    className={`nav-item${current ? " selected" : ""}`}
                    href={item.href}
                    key={item.href}
                    aria-current={current ? "page" : undefined}
                  >
                    <span className="nav-dot" aria-hidden="true">
                      {item.label.charAt(0)}
                    </span>
                    {(role && item.labelFor?.[role]) ?? item.label}
                  </Link>
                );
              })
            : null}
          {ready && (
            <div className="nav-secondary">
              {config.secondary.map((item) => (
                <Link
                  className={`nav-link${pathname === item.href ? " selected" : ""}`}
                  href={item.href}
                  key={item.href}
                  aria-current={pathname === item.href ? "page" : undefined}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          )}
          <p className="nav-footnote">
            Clinic connections stay separate. Switching clinics never shares records between them.
          </p>
        </nav>
        <main className="portal-content app-main" id="app-main" tabIndex={-1}>
          {content}
        </main>
      </div>
    </div>
  );
}

/** Shows `children` only when the active clinic role is allowed; otherwise explains why. */
export function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { active } = usePortal();
  if (active && roles.includes(active.role as Role)) {
    return <>{children}</>;
  }
  const allowed = roles.map((role) => ROLE_LABELS[role]).join(" or ");
  return (
    <div className="state-panel state-problem state-forbidden" role="alert">
      <span className="state-icon" aria-hidden="true">⊘</span>
      <div>
        <h3>This area isn&apos;t available for your role</h3>
        <p>
          It&apos;s for {allowed.toLowerCase()} accounts. Your role at {active?.tenant_name ?? "this clinic"} is{" "}
          {ROLE_LABELS[active?.role ?? ""]?.toLowerCase() ?? "not set"}.
        </p>
      </div>
    </div>
  );
}
