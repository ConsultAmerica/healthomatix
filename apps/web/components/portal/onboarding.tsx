"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { api, call, type ApiProblem } from "@/lib/api";
import { browserTimeZone } from "@/lib/time";
import { FormError, Notice, SelectField, SubmitButton, TextField, useToast } from "@/components/ui";
import { DEMO_PERSONAS } from "@/lib/demo-personas";
import { ROLE_LABELS, usePortal, type DemoInfo, type PortalKind } from "./portal-context";

const AUTH_ERRORS: Record<string, string> = {
  sign_in_unavailable: "Sign-in isn't configured for this environment yet.",
  identity_unreachable: "The sign-in service couldn't be reached. Try again in a moment.",
  access_denied: "Sign-in was cancelled.",
  sign_in_expired: "That sign-in attempt expired. Please start again.",
  sign_in_failed: "Sign-in couldn't be completed. Please try again.",
  session_too_large: "Your identity provider returned a session that is too large for this browser. Contact support.",
  demo_unavailable: "Demo mode isn't turned on for this environment.",
  demo_failed: "That demo account isn't available. Choose another.",
  demo_passcode: "That demo passcode isn't right. Check it and try again.",
};

export function SignInPanel({
  kind,
  configured,
  expired,
  authError,
  returnTo,
  demo,
}: {
  kind: PortalKind;
  configured: boolean;
  expired: boolean;
  authError: string | null;
  returnTo: string;
  demo: DemoInfo;
}) {
  const audience = kind === "clinic" ? "clinic workspace" : "patient space";
  return (
    <div className="sign-in-panel">
      <p className="eyebrow">{kind === "clinic" ? "CLINIC WORKSPACE" : "PATIENT SPACE"}</p>
      <h1>
        {expired ? "Your session has ended" : demo.enabled && !configured ? "Choose a demo account" : `Sign in to your ${audience}`}
      </h1>
      <p className="lead">
        {kind === "clinic"
          ? "Manage your clinic, team, providers, and schedule in one secure place."
          : "See your appointments, records, and consent choices with your clinic."}
      </p>
      {authError && (
        <div className="form-error" role="alert">
          <strong>We couldn&apos;t sign you in</strong>
          <p>{AUTH_ERRORS[authError] ?? AUTH_ERRORS.sign_in_failed}</p>
        </div>
      )}
      {configured && (
        <div className="portal-actions">
          <a className="button" href={`/auth/login?returnTo=${encodeURIComponent(returnTo)}`}>
            {expired ? "Sign in again" : "Sign in"}
          </a>
        </div>
      )}
      {demo.enabled && <DemoSignIn kind={kind} returnTo={returnTo} passcodeRequired={demo.passcodeRequired} />}
      {!configured && !demo.enabled && (
        <>
          <Notice title="Sign-in isn't available in this environment" tone="warning">
            Secure sign-in has not been set up for this deployment, so no account information can be shown.
          </Notice>
          <details className="system-details">
            <summary>Setup details for administrators</summary>
            <p className="system-details-copy">
              Set <code>OIDC_ISSUER</code>, <code>OIDC_CLIENT_ID</code>, <code>APP_BASE_URL</code>,{" "}
              <code>SESSION_SECRET</code> (32+ characters), and <code>HEALTHOMATIX_API_URL</code> for the web app,
              then register <code>{"{APP_BASE_URL}"}/auth/callback</code> as a redirect URI with your identity
              provider.
            </p>
          </details>
        </>
      )}
      {!demo.enabled && (
        <ul className="trust-list">
          <li>Your sign-in is handled by your organization&apos;s identity provider.</li>
          <li>Access tokens stay on the server and are never stored in this browser.</li>
          <li>Each clinic&apos;s records stay separate.</li>
        </ul>
      )}
    </div>
  );
}

function DemoSignIn({
  kind,
  returnTo,
  passcodeRequired,
}: {
  kind: PortalKind;
  returnTo: string;
  passcodeRequired: boolean;
}) {
  // Show this portal's roles first.
  const personas = [...DEMO_PERSONAS].sort((a, b) => Number(b.portal === kind) - Number(a.portal === kind));
  return (
    <form className="demo-sign-in" method="post" action="/auth/demo">
      <Notice title="Demo mode — synthetic data only" tone="warning">
        These shared test accounts skip real sign-in. Never enter real patient information.
      </Notice>
      <input type="hidden" name="returnTo" value={returnTo} />
      {passcodeRequired && (
        <TextField label="Demo passcode" name="passcode" type="password" required autoComplete="off" />
      )}
      <div className="persona-grid">
        {personas.map((persona) => (
          <button className="persona-card" type="submit" name="persona" value={persona.id} key={persona.id}>
            <span className="persona-portal">{persona.portal === "clinic" ? "Clinic workspace" : "Patient space"}</span>
            <strong>{persona.label}</strong>
            <span>{persona.hint}</span>
          </button>
        ))}
      </div>
      <details className="system-details">
        <summary>How to test the full flow</summary>
        <ol className="system-details-copy demo-steps">
          <li>Sign in as <strong>Clinic admin</strong> and create a clinic.</li>
          <li>On <strong>Team</strong>, create invitation codes for a provider and a patient.</li>
          <li>Switch to <strong>Provider</strong> from the demo bar, join with the code, then complete the profile and add a credential.</li>
          <li>Switch back to <strong>Clinic admin</strong> and verify the credential under <strong>Providers</strong>.</li>
          <li>As <strong>Provider</strong>, add availability. As <strong>Patient</strong>, join and book. (Scheduling must be enabled on the API.)</li>
        </ol>
      </details>
    </form>
  );
}

export function NoMembership({ kind }: { kind: PortalKind }) {
  return (
    <div className="onboarding">
      <p className="eyebrow">WELCOME</p>
      <h1>{kind === "clinic" ? "Set up your clinic workspace" : "Connect with your clinic"}</h1>
      <p className="lead">
        {kind === "clinic"
          ? "You're signed in but not yet part of a clinic. Create a new clinic, or join one with an invitation code from a clinic administrator."
          : "You're signed in but not yet connected to a clinic. Enter the invitation code your clinic shared with you."}
      </p>
      <div className={kind === "clinic" ? "onboarding-grid" : ""}>
        {kind === "clinic" && (
          <div className="app-card">
            <h2 className="card-title">Create a clinic</h2>
            <p className="card-copy">You&apos;ll become the clinic administrator.</p>
            <CreateClinicForm />
          </div>
        )}
        <div className="app-card">
          <h2 className="card-title">Join with an invitation</h2>
          <p className="card-copy">Invitation codes are single-use and expire after seven days.</p>
          <JoinClinicForm />
        </div>
      </div>
    </div>
  );
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
}

export function timeZoneOptions(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [browserTimeZone()];
  }
}

export function CreateClinicForm() {
  const router = useRouter();
  const notify = useToast();
  const { refresh, selectTenant } = usePortal();
  const zones = useMemo(timeZoneOptions, []);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [locationName, setLocationName] = useState("Main clinic");
  const [timezone, setTimezone] = useState(browserTimeZone());
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const effectiveSlug = slugEdited ? slug : slugify(name);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants", {
        body: { display_name: name, slug: effectiveSlug, location_name: locationName, timezone },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(
        result.problem.code === "CLINIC_SLUG_UNAVAILABLE"
          ? { ...result.problem, fields: { slug: "This web address is already taken. Try another." } }
          : result.problem,
      );
      return;
    }
    notify(`${result.data.display_name} is ready.`);
    selectTenant(result.data.tenant_id);
    refresh();
    router.push("/clinic");
  }

  return (
    <form className="form-stack" onSubmit={submit} noValidate={false}>
      <FormError problem={problem} />
      <TextField
        label="Clinic name"
        required
        minLength={2}
        maxLength={200}
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={problem?.fields.display_name}
        autoComplete="organization"
      />
      <TextField
        label="Clinic web address"
        required
        minLength={3}
        maxLength={96}
        pattern="[a-z0-9]+(-[a-z0-9]+)*"
        value={effectiveSlug}
        onChange={(event) => {
          setSlugEdited(true);
          setSlug(event.target.value.toLowerCase());
        }}
        hint="Lowercase letters, numbers, and hyphens. Used to identify your clinic."
        error={problem?.fields.slug}
      />
      <div className="form-row">
        <TextField
          label="First location"
          required
          minLength={2}
          maxLength={160}
          value={locationName}
          onChange={(event) => setLocationName(event.target.value)}
          error={problem?.fields.location_name}
        />
        <SelectField
          label="Time zone"
          required
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          error={problem?.fields.timezone}
        >
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone.replaceAll("_", " ")}
            </option>
          ))}
        </SelectField>
      </div>
      <div className="form-actions">
        <SubmitButton pending={pending} pendingLabel="Creating clinic…">
          Create clinic
        </SubmitButton>
      </div>
    </form>
  );
}

export function JoinClinicForm() {
  const router = useRouter();
  const notify = useToast();
  const { refresh } = usePortal();
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const messages: Record<string, string> = {
    INVITATION_NOT_FOUND: "This code isn't valid or has already been used. Check it with your clinic.",
    INVITATION_EXPIRED: "This invitation has expired. Ask your clinic for a new code.",
    MEMBERSHIP_EXISTS: "You're already a member of this clinic.",
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setProblem(null);
    const result = await call(api().POST("/api/v1/invitations/accept", { body: { invitation_code: code.trim() } }));
    setPending(false);
    if (!result.ok) {
      const message = messages[result.problem.code];
      setProblem(message ? { ...result.problem, message } : result.problem);
      return;
    }
    // A patient code accepted from the clinic portal (or vice versa) lands in the matching portal.
    const joinedRole = result.data.role;
    notify(`You've joined as ${ROLE_LABELS[joinedRole]?.toLowerCase() ?? joinedRole}.`);
    setCode("");
    refresh();
    router.push(joinedRole === "patient" ? "/patient" : "/clinic");
  }

  return (
    <form className="form-stack" onSubmit={submit}>
      <FormError problem={problem} />
      <TextField
        label="Invitation code"
        required
        minLength={32}
        maxLength={128}
        value={code}
        onChange={(event) => setCode(event.target.value)}
        autoComplete="off"
        spellCheck={false}
        hint="Paste the full code exactly as it was shared with you."
        error={problem?.fields.invitation_code}
      />
      <div className="form-actions">
        <SubmitButton pending={pending} pendingLabel="Joining…">
          Join clinic
        </SubmitButton>
      </div>
    </form>
  );
}
