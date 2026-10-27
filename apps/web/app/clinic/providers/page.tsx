"use client";

import { useEffect, useState, type FormEvent } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import {
  Dialog,
  EmptyState,
  FormError,
  Notice,
  PageHeader,
  QueryView,
  Section,
  SelectField,
  StatusBadge,
  SubmitButton,
  Table,
  TextField,
  humanize,
  useToast,
} from "@/components/ui";
import { api, call, callOptional, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDate, formatDateTime, shortId } from "@/lib/time";

export default function ProvidersPage() {
  const { role } = useActiveMembership();
  return (
    <RoleGate roles={["tenant_admin", "provider"]}>
      {role === "tenant_admin" ? <CredentialReview /> : <ProviderSelfService />}
    </RoleGate>
  );
}

/* ——— Administrator: credential review queue ——— */

type QueueStatus = "pending" | "verified" | "rejected";
type QueueItem = Schemas["CredentialReviewQueueRead"];

function CredentialReview() {
  const { tenant_id } = useActiveMembership();
  const notify = useToast();
  const [status, setStatus] = useState<QueueStatus>("pending");
  const [reviewing, setReviewing] = useState<QueueItem | null>(null);
  const [decision, setDecision] = useState<"verified" | "rejected">("verified");
  const [source, setSource] = useState("");
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const { state, reload } = useApiQuery(`credential-queue:${tenant_id}:${status}`, () =>
    call(
      api().GET("/api/v1/tenants/{tenant_id}/provider-credentials", {
        params: { path: { tenant_id }, query: { status } },
      }),
    ),
  );

  function open(item: QueueItem) {
    setReviewing(item);
    setDecision("verified");
    setSource("");
    setProblem(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reviewing) return;
    setPending(true);
    setProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/providers/{provider_user_id}/credentials/{credential_id}/review", {
        params: {
          path: { tenant_id, provider_user_id: reviewing.provider_user_id, credential_id: reviewing.credential_id },
        },
        body: { decision, review_source: source },
      }),
    );
    setPending(false);
    if (!result.ok) {
      setProblem(
        result.problem.code === "CREDENTIAL_NOT_FOUND"
          ? { ...result.problem, message: "This credential was already reviewed or withdrawn. Refresh the list." }
          : result.problem,
      );
      return;
    }
    notify(decision === "verified" ? "Credential verified." : "Credential rejected.");
    setReviewing(null);
    reload();
  }

  return (
    <>
      <PageHeader
        eyebrow="PROVIDERS"
        title="Credential review"
        description="Verify provider credentials against the issuing regulator before they can offer appointments. Providers can't verify their own credentials."
      />

      <div className="segmented" role="tablist" aria-label="Credential status">
        {(["pending", "verified", "rejected"] as QueueStatus[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={status === value}
            className={status === value ? "is-active" : ""}
            onClick={() => setStatus(value)}
          >
            {value === "pending" ? "Awaiting review" : humanize(value)}
          </button>
        ))}
      </div>

      <QueryView state={state} onRetry={reload} rows={4} loadingLabel="Loading credentials">
        {(items) =>
          items.length ? (
            <Table caption={`${humanize(status)} credentials`}>
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col">Credential</th>
                  <th scope="col">Regulator</th>
                  <th scope="col">Submitted</th>
                  <th scope="col">Status</th>
                  {status === "pending" && (
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.credential_id}>
                    <td>
                      <strong className="cell-title">{item.provider_display_name || "Name not provided"}</strong>
                      <span className="cell-sub">
                        {item.provider_specialty || "Specialty not set"} · Ref {shortId(item.provider_user_id)}
                      </span>
                    </td>
                    <td>
                      {humanize(item.credential_type)}
                      <span className="cell-sub">{item.jurisdiction}</span>
                    </td>
                    <td>{item.regulator}</td>
                    <td>{formatDate(item.submitted_at)}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    {status === "pending" && (
                      <td className="cell-actions">
                        <button className="button button-small" type="button" onClick={() => open(item)}>
                          Review
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title={status === "pending" ? "You're all caught up" : `No ${status} credentials`}>
              {status === "pending" ? "New submissions from providers will appear here." : undefined}
            </EmptyState>
          )
        }
      </QueryView>

      <Dialog
        open={reviewing !== null}
        onClose={() => setReviewing(null)}
        title="Review credential"
        description={
          reviewing
            ? `${humanize(reviewing.credential_type)} · ${reviewing.jurisdiction} · ${reviewing.regulator}`
            : undefined
        }
      >
        <form className="form-stack" onSubmit={submit}>
          <FormError problem={problem} />
          <fieldset className="choice-group">
            <legend>Decision</legend>
            <label className="choice">
              <input
                type="radio"
                name="decision"
                value="verified"
                checked={decision === "verified"}
                onChange={() => setDecision("verified")}
              />
              <span>
                <strong>Verify</strong> — the credential is valid and in good standing.
              </span>
            </label>
            <label className="choice">
              <input
                type="radio"
                name="decision"
                value="rejected"
                checked={decision === "rejected"}
                onChange={() => setDecision("rejected")}
              />
              <span>
                <strong>Reject</strong> — the credential couldn&apos;t be confirmed.
              </span>
            </label>
          </fieldset>
          <TextField
            label="How did you check this?"
            required
            minLength={2}
            maxLength={512}
            value={source}
            onChange={(event) => setSource(event.target.value)}
            hint="For example, the regulator's public register lookup and date. This is kept in the audit trail."
            error={problem?.fields.review_source}
          />
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setReviewing(null)}>
              Cancel
            </button>
            <SubmitButton
              pending={pending}
              pendingLabel="Saving…"
              className={`button button-small${decision === "rejected" ? " button-danger" : ""}`}
            >
              {decision === "verified" ? "Verify credential" : "Reject credential"}
            </SubmitButton>
          </div>
        </form>
      </Dialog>
    </>
  );
}

/* ——— Provider: own profile and credentials ——— */

const CREDENTIAL_TYPES = [
  ["medical_license", "Medical license"],
  ["nursing_license", "Nursing license"],
  ["board_certification", "Board certification"],
  ["controlled_substance_registration", "Controlled substance registration"],
  ["other", "Other professional credential"],
] as const;

function ProviderSelfService() {
  const { tenant_id } = useActiveMembership();
  const notify = useToast();
  const path = { params: { path: { tenant_id } } };

  const profile = useApiQuery(`provider-profile:${tenant_id}`, () =>
    callOptional(api().GET("/api/v1/tenants/{tenant_id}/providers/me", path), "PROFILE_NOT_FOUND"));
  const credentials = useApiQuery(`own-credentials:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/providers/me/credentials", path)),
  );

  const [displayName, setDisplayName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [profilePending, setProfilePending] = useState(false);
  const [profileProblem, setProfileProblem] = useState<ApiProblem | null>(null);

  useEffect(() => {
    if (profile.state.status === "success" && profile.state.data) {
      setDisplayName(profile.state.data.display_name);
      setSpecialty(profile.state.data.specialty);
    }
  }, [profile.state]);

  const [credentialOpen, setCredentialOpen] = useState(false);
  const [credential, setCredential] = useState({
    credential_type: "medical_license",
    jurisdiction: "",
    regulator: "",
    verification_reference: "",
  });
  const [credentialPending, setCredentialPending] = useState(false);
  const [credentialProblem, setCredentialProblem] = useState<ApiProblem | null>(null);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setProfilePending(true);
    setProfileProblem(null);
    const result = await call(
      api().PUT("/api/v1/tenants/{tenant_id}/providers/me", {
        ...path,
        body: { display_name: displayName, specialty },
      }),
    );
    setProfilePending(false);
    if (!result.ok) {
      setProfileProblem(result.problem);
      return;
    }
    notify("Profile saved.");
    profile.reload();
  }

  async function submitCredential(event: FormEvent) {
    event.preventDefault();
    setCredentialPending(true);
    setCredentialProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/providers/me/credentials", { ...path, body: credential }),
    );
    setCredentialPending(false);
    if (!result.ok) {
      setCredentialProblem(result.problem);
      return;
    }
    notify("Credential submitted for review.");
    setCredentialOpen(false);
    setCredential({ credential_type: "medical_license", jurisdiction: "", regulator: "", verification_reference: "" });
    credentials.reload();
  }

  const profileData = profile.state.status === "success" ? profile.state.data : null;
  const hasVerified =
    credentials.state.status === "success" && credentials.state.data.some((item) => item.status === "verified");

  return (
    <>
      <PageHeader
        eyebrow="MY PROFILE"
        title="Provider profile"
        description="Patients see your name and specialty when booking. You can offer appointments once your profile is active and a credential is verified."
      />

      {profileData && (
        <div className="readiness-strip">
          <span>
            Profile <StatusBadge status={profileData.profile_status} />
          </span>
          <span>
            Credential <StatusBadge status={hasVerified ? "verified" : "pending"}>{hasVerified ? "Verified" : "Not yet verified"}</StatusBadge>
          </span>
        </div>
      )}

      <Section title="Profile details">
        <QueryView state={profile.state} onRetry={profile.reload} rows={2}>
          {(data) => (
            <form className="form-stack app-card" onSubmit={saveProfile}>
              {!data && (
                <Notice title="Create your profile">Add the name and specialty patients will see.</Notice>
              )}
              <FormError problem={profileProblem} />
              <div className="form-row">
                <TextField
                  label="Display name"
                  required
                  maxLength={200}
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  hint="As you'd like patients to see it, e.g. Dr. Alex Morgan"
                  error={profileProblem?.fields.display_name}
                />
                <TextField
                  label="Specialty"
                  maxLength={120}
                  value={specialty}
                  onChange={(event) => setSpecialty(event.target.value)}
                  error={profileProblem?.fields.specialty}
                />
              </div>
              <div className="form-actions">
                {data && <span className="muted">Last updated {formatDateTime(data.updated_at)}</span>}
                <SubmitButton pending={profilePending}>{data ? "Save changes" : "Create profile"}</SubmitButton>
              </div>
            </form>
          )}
        </QueryView>
      </Section>

      <Section
        title="Credentials"
        description="A clinic administrator verifies each credential with the issuing regulator."
        actions={
          <button className="button button-small" type="button" onClick={() => setCredentialOpen(true)}>
            Add credential
          </button>
        }
      >
        <QueryView state={credentials.state} onRetry={credentials.reload} rows={2}>
          {(items) =>
            items.length ? (
              <Table caption="Your credentials">
                <thead>
                  <tr>
                    <th scope="col">Credential</th>
                    <th scope="col">Regulator</th>
                    <th scope="col">Submitted</th>
                    <th scope="col">Reviewed</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.credential_id}>
                      <td>
                        {humanize(item.credential_type)}
                        <span className="cell-sub">{item.jurisdiction}</span>
                      </td>
                      <td>{item.regulator}</td>
                      <td>{formatDate(item.submitted_at)}</td>
                      <td>{item.reviewed_at ? formatDate(item.reviewed_at) : <span className="muted">Awaiting review</span>}</td>
                      <td>
                        <StatusBadge status={item.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState
                title="No credentials yet"
                action={
                  <button className="button button-small" type="button" onClick={() => setCredentialOpen(true)}>
                    Add your first credential
                  </button>
                }
              >
                Add the license or certification that allows you to practice.
              </EmptyState>
            )
          }
        </QueryView>
      </Section>

      <Dialog
        open={credentialOpen}
        onClose={() => setCredentialOpen(false)}
        title="Add a credential"
        description="Your clinic administrator will verify this with the regulator. Don't include license documents here."
      >
        <form className="form-stack" onSubmit={submitCredential}>
          <FormError problem={credentialProblem} />
          <SelectField
            label="Credential type"
            required
            value={credential.credential_type}
            onChange={(event) => setCredential({ ...credential, credential_type: event.target.value })}
          >
            {CREDENTIAL_TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          <div className="form-row">
            <TextField
              label="Jurisdiction"
              required
              minLength={2}
              maxLength={32}
              value={credential.jurisdiction}
              onChange={(event) => setCredential({ ...credential, jurisdiction: event.target.value })}
              hint="Country or region code, e.g. US-NY"
              error={credentialProblem?.fields.jurisdiction}
            />
            <TextField
              label="Issuing regulator"
              required
              minLength={2}
              maxLength={200}
              value={credential.regulator}
              onChange={(event) => setCredential({ ...credential, regulator: event.target.value })}
              error={credentialProblem?.fields.regulator}
            />
          </div>
          <TextField
            label="License or registration number"
            maxLength={512}
            value={credential.verification_reference}
            onChange={(event) => setCredential({ ...credential, verification_reference: event.target.value })}
            hint="Optional. Helps the reviewer find you on the public register."
            error={credentialProblem?.fields.verification_reference}
          />
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setCredentialOpen(false)}>
              Cancel
            </button>
            <SubmitButton pending={credentialPending} pendingLabel="Submitting…">
              Submit for review
            </SubmitButton>
          </div>
        </form>
      </Dialog>
    </>
  );
}
