"use client";

import { useState } from "react";
import { Dialog, Notice } from "@/components/ui";

const PROVIDERS = [
  {
    id: "oidc",
    label: "Enterprise OIDC / OAuth 2.0",
    detail: "Authorization-code + PKCE against your organization’s IdP (Okta, Auth0, Entra ID).",
    badge: "Production path",
  },
  {
    id: "smart",
    label: "SMART on FHIR",
    detail: "EHR launch context with patient/encounter scopes—tokens stay server-side via the BFF.",
    badge: "Interop",
  },
  {
    id: "entra",
    label: "Microsoft Entra ID",
    detail: "Work or school accounts with conditional access and MFA enforced by IdP policy.",
    badge: "Enterprise",
  },
] as const;

/**
 * Preview-only SSO chooser. Does not start a real OAuth dance—shows how production
 * sign-in would be selected when an identity provider is wired.
 */
export function MockSsoButton({ demoEnabled }: { demoEnabled: boolean }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<(typeof PROVIDERS)[number] | null>(null);

  return (
    <>
      <button className="button button-light" type="button" onClick={() => { setPicked(null); setOpen(true); }}>
        Preview enterprise sign-in
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title={picked ? picked.label : "How production sign-in would work"}
        description={
          picked
            ? "This environment is not connected to an identity provider. The flow below is a structural preview."
            : "Choose a protocol to see the security posture Healthomatix expects in production."
        }
      >
        {!picked ? (
          <ul className="mock-sso-list">
            {PROVIDERS.map((provider) => (
              <li key={provider.id}>
                <button className="mock-sso-option" type="button" onClick={() => setPicked(provider)}>
                  <span className="mock-sso-badge">{provider.badge}</span>
                  <strong>{provider.label}</strong>
                  <span>{provider.detail}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mock-sso-detail">
            <ol className="mock-sso-steps">
              <li>Browser redirects to the IdP authorize endpoint (PKCE challenge).</li>
              <li>MFA / conditional access runs entirely at the identity provider.</li>
              <li>Callback exchanges the code server-side; tokens never reach page script.</li>
              <li>
                {picked.id === "smart"
                  ? "SMART launch context binds patient/encounter scopes to the session."
                  : "Session cookie is encrypted HttpOnly; API calls use the BFF proxy."}
              </li>
            </ol>
            <Notice title="Preview only — no live federation" tone="warning">
              Secure browser sign-in is intentionally unconfigured here.{" "}
              {demoEnabled
                ? "Use a demo account below to explore synthetic workflows."
                : "Ask an administrator to set OIDC_* and SESSION_SECRET, or enable DEMO_AUTH_SECRET for sandbox accounts."}
            </Notice>
            <div className="form-actions">
              <button className="button button-light button-small" type="button" onClick={() => setPicked(null)}>
                Back to options
              </button>
              <button className="button button-small" type="button" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>
          </div>
        )}
      </Dialog>
    </>
  );
}
