"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { BrandMark } from "@/app/brand-mark";
import { Icon, type IconName } from "@/components/icons";
import { LoadingState, ProblemState, ToastProvider } from "@/components/ui";
import { DEMO_PERSONAS, findPersona } from "@/lib/demo-personas";
import { NoMembership, SignInPanel } from "./onboarding";
import { PortalProvider, ROLE_LABELS, usePortal, type PortalKind, type Role } from "./portal-context";

export type NavItem = {
  label: string;
  href: string;
  icon?: IconName;
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
  const { state, demo, memberships, active, selectTenant, refresh } = usePortal();
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
        demo={demo}
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
    <div className={`portal-shell ${config.kind}-shell app-shell${ready ? "" : " is-signed-out"}`}>
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
          {ready ? (
            <div className="account-chip">
              <span className="account-avatar" aria-hidden="true">
                {initials(findPersona(demo.user)?.label ?? ROLE_LABELS[role ?? ""] ?? "You")}
              </span>
              <span className="account-text">
                <strong>{findPersona(demo.user)?.label ?? ROLE_LABELS[role ?? ""] ?? "Signed in"}</strong>
                {memberships.length <= 1 && <span>{active?.tenant_name ?? "No clinic yet"}</span>}
              </span>
              <form method="post" action="/auth/logout">
                <input type="hidden" name="returnTo" value={pathname} />
                <button className="icon-button account-signout" type="submit" title="Sign out">
                  <Icon name="logout" />
                  <span className="visually-hidden">Sign out</span>
                </button>
              </form>
            </div>
          ) : (
            <Link className="topbar-home" href="/">
              Home
            </Link>
          )}
        </div>
      </header>
      {ready && demo.user && <DemoBar current={demo.user} pathname={pathname} />}
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
                    <Icon name={item.icon ?? "home"} className="nav-icon" />
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

function initials(label: string): string {
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join("");
}

function DemoBar({ current, pathname }: { current: string; pathname: string }) {
  const persona = findPersona(current);
  return (
    <div className="demo-bar" role="region" aria-label="Demo mode">
      <p>
        <span className="demo-tag">Demo</span>
        Signed in as <strong>{persona?.label ?? current}</strong>
        <span className="demo-bar-note"> · Synthetic data only — never enter real patient information.</span>
      </p>
      <form className="demo-switch" method="post" action="/auth/demo">
        <input type="hidden" name="returnTo" value={pathname} />
        <label>
          <span className="visually-hidden">Switch demo user</span>
          <select name="persona" defaultValue={current}>
            {DEMO_PERSONAS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Switch</button>
      </form>
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
