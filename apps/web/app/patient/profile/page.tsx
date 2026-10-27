"use client";

import { useEffect, useState, type FormEvent } from "react";
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
  TextField,
  useToast,
} from "@/components/ui";
import { api, call, callOptional, useApiQuery, type ApiProblem, type Schemas } from "@/lib/api";
import { formatDate, formatDateTime, isFuture } from "@/lib/time";

type Consent = Schemas["ConsentRead"];

/**
 * Consent choices offered to patients. Grants record the clinic's published
 * policy version, so granting is only enabled when one is configured.
 */
const CONSENT_POLICY_VERSION = process.env.NEXT_PUBLIC_CONSENT_POLICY_VERSION ?? "";
const CONSENT_OPTIONS = [
  {
    purpose: "care_coordination",
    scope: "clinic_care_team",
    title: "Share my information with my care team",
    detail: "Lets providers at this clinic who are involved in your care see the information you've shared.",
  },
  {
    purpose: "appointment_communication",
    scope: "contact_details",
    title: "Contact me about my appointments",
    detail: "Lets the clinic use your contact details for appointment confirmations and changes.",
  },
] as const;

const WITHDRAW_REASONS = [
  ["no_longer_wanted", "I no longer want this"],
  ["changing_clinic", "I'm moving my care elsewhere"],
  ["privacy_concern", "Privacy concern"],
  ["other", "Other reason"],
] as const;

const LANGUAGES = [
  ["en", "English"],
  ["es", "Español"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["pt", "Português"],
  ["zh", "中文"],
  ["ar", "العربية"],
  ["hi", "हिन्दी"],
  ["ur", "اردو"],
] as const;

function consentState(consent: Consent): "active" | "withdrawn" | "expired" {
  if (consent.withdrawn_at) return "withdrawn";
  if (consent.expires_at && !isFuture(consent.expires_at)) return "expired";
  return "active";
}

function consentTitle(consent: Consent): string {
  return (
    CONSENT_OPTIONS.find((option) => option.purpose === consent.purpose)?.title ??
    consent.purpose.replaceAll("_", " ")
  );
}

export default function ProfilePage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const notify = useToast();
  const path = { params: { path: { tenant_id } } };

  const profile = useApiQuery(`patient-profile:${tenant_id}`, () =>
    callOptional(api().GET("/api/v1/tenants/{tenant_id}/patients/me", path), "PROFILE_NOT_FOUND"));
  const consents = useApiQuery(`consents:${tenant_id}`, () =>
    call(api().GET("/api/v1/tenants/{tenant_id}/patients/me/consents", path)),
  );

  const [form, setForm] = useState({ preferred_name: "", legal_name: "", phone: "", preferred_language: "en" });
  const [saving, setSaving] = useState(false);
  const [profileProblem, setProfileProblem] = useState<ApiProblem | null>(null);

  useEffect(() => {
    if (profile.state.status === "success" && profile.state.data) {
      const { preferred_name, legal_name, phone, preferred_language } = profile.state.data;
      setForm({ preferred_name, legal_name, phone, preferred_language });
    }
  }, [profile.state]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setProfileProblem(null);
    const result = await call(api().PUT("/api/v1/tenants/{tenant_id}/patients/me", { ...path, body: form }));
    setSaving(false);
    if (!result.ok) {
      setProfileProblem(result.problem);
      return;
    }
    notify("Profile saved.");
    profile.reload();
  }

  const [granting, setGranting] = useState<string | null>(null);
  const [consentProblem, setConsentProblem] = useState<ApiProblem | null>(null);

  async function grant(option: (typeof CONSENT_OPTIONS)[number]) {
    setGranting(option.purpose);
    setConsentProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/patients/me/consents", {
        ...path,
        body: { purpose: option.purpose, scope: option.scope, policy_version: CONSENT_POLICY_VERSION },
      }),
    );
    setGranting(null);
    if (!result.ok) {
      setConsentProblem(result.problem);
      return;
    }
    notify("Consent recorded.");
    consents.reload();
  }

  const [withdrawing, setWithdrawing] = useState<Consent | null>(null);
  const [reason, setReason] = useState<string>(WITHDRAW_REASONS[0][0]);
  const [withdrawPending, setWithdrawPending] = useState(false);
  const [withdrawProblem, setWithdrawProblem] = useState<ApiProblem | null>(null);

  async function withdraw(event: FormEvent) {
    event.preventDefault();
    if (!withdrawing) return;
    setWithdrawPending(true);
    setWithdrawProblem(null);
    const result = await call(
      api().POST("/api/v1/tenants/{tenant_id}/patients/me/consents/{consent_id}/withdraw", {
        params: { path: { tenant_id, consent_id: withdrawing.grant_id } },
        body: { reason_code: reason },
      }),
    );
    setWithdrawPending(false);
    if (!result.ok) {
      setWithdrawProblem(result.problem);
      return;
    }
    setWithdrawing(null);
    notify("Consent withdrawn.");
    consents.reload();
  }

  const consentList = consents.state.status === "success" ? consents.state.data : [];
  const activePurposes = new Set(consentList.filter((item) => consentState(item) === "active").map((item) => item.purpose));

  return (
    <>
      <PageHeader
        eyebrow="PROFILE & CONSENT"
        title="Your information"
        description={`What ${tenant_name} knows about you, and the choices you've made about how it's used.`}
      />

      <Section title="Profile">
        <QueryView state={profile.state} onRetry={profile.reload} rows={3}>
          {(data) => (
            <form className="form-stack app-card" onSubmit={saveProfile}>
              <FormError problem={profileProblem} />
              <div className="form-row">
                <TextField
                  label="Preferred name"
                  maxLength={120}
                  value={form.preferred_name}
                  onChange={(event) => setForm({ ...form, preferred_name: event.target.value })}
                  hint="What you'd like to be called."
                  autoComplete="nickname"
                  error={profileProblem?.fields.preferred_name}
                />
                <TextField
                  label="Legal name"
                  maxLength={200}
                  value={form.legal_name}
                  onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
                  hint="As it appears on your ID or insurance."
                  autoComplete="name"
                  error={profileProblem?.fields.legal_name}
                />
              </div>
              <div className="form-row">
                <TextField
                  label="Phone"
                  type="tel"
                  maxLength={40}
                  value={form.phone}
                  onChange={(event) => setForm({ ...form, phone: event.target.value })}
                  autoComplete="tel"
                  error={profileProblem?.fields.phone}
                />
                <SelectField
                  label="Preferred language"
                  value={form.preferred_language}
                  onChange={(event) => setForm({ ...form, preferred_language: event.target.value })}
                  error={profileProblem?.fields.preferred_language}
                >
                  {LANGUAGES.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                  {!LANGUAGES.some(([code]) => code === form.preferred_language) && (
                    <option value={form.preferred_language}>{form.preferred_language}</option>
                  )}
                </SelectField>
              </div>
              <div className="form-actions">
                {data && <span className="muted">Last updated {formatDateTime(data.updated_at)}</span>}
                <SubmitButton pending={saving}>{data ? "Save changes" : "Save profile"}</SubmitButton>
              </div>
            </form>
          )}
        </QueryView>
      </Section>

      <Section
        title="Consent"
        description="You can change your mind at any time. Withdrawing consent is recorded and doesn't erase your history."
      >
        <FormError problem={consentProblem} />
        {CONSENT_POLICY_VERSION ? (
          <div className="consent-options">
            {CONSENT_OPTIONS.map((option) => {
              const active = activePurposes.has(option.purpose);
              return (
                <div className="consent-option app-card" key={option.purpose}>
                  <div>
                    <h3 className="card-title">{option.title}</h3>
                    <p className="card-copy">{option.detail}</p>
                  </div>
                  {active ? (
                    <StatusBadge status="active">Granted</StatusBadge>
                  ) : (
                    <button
                      className="button button-small"
                      type="button"
                      onClick={() => grant(option)}
                      disabled={granting !== null || consents.state.status !== "success"}
                      aria-busy={granting === option.purpose}
                    >
                      {granting === option.purpose ? "Saving…" : "Give consent"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <Notice title="Consent forms aren't published yet">
            {tenant_name} hasn&apos;t published its consent policy online. You can still review and withdraw any consent
            you&apos;ve given below.
          </Notice>
        )}

        <h3 className="subheading">History</h3>
        <QueryView state={consents.state} onRetry={consents.reload} rows={2}>
          {(items) =>
            items.length ? (
              <ul className="consent-history">
                {items.map((item) => {
                  const status = consentState(item);
                  return (
                    <li key={item.grant_id}>
                      <div>
                        <strong>{consentTitle(item)}</strong>
                        <span className="cell-sub">
                          Given {formatDate(item.granted_at)} · Policy {item.policy_version}
                          {item.withdrawn_at && <> · Withdrawn {formatDate(item.withdrawn_at)}</>}
                          {item.expires_at && !item.withdrawn_at && <> · Expires {formatDate(item.expires_at)}</>}
                        </span>
                      </div>
                      <div className="item-actions">
                        <StatusBadge status={status} />
                        {status === "active" && (
                          <button
                            className="button button-ghost-danger button-small"
                            type="button"
                            onClick={() => {
                              setWithdrawProblem(null);
                              setReason(WITHDRAW_REASONS[0][0]);
                              setWithdrawing(item);
                            }}
                          >
                            Withdraw
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState title="No consent recorded yet" />
            )
          }
        </QueryView>
      </Section>

      <Dialog
        open={withdrawing !== null}
        onClose={() => setWithdrawing(null)}
        title="Withdraw consent?"
        description={withdrawing ? `${consentTitle(withdrawing)}. This takes effect immediately.` : undefined}
      >
        <form className="form-stack" onSubmit={withdraw}>
          <FormError problem={withdrawProblem} />
          <SelectField label="Reason" value={reason} onChange={(event) => setReason(event.target.value)}>
            {WITHDRAW_REASONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
          <div className="form-actions">
            <button className="button button-light button-small" type="button" onClick={() => setWithdrawing(null)}>
              Keep consent
            </button>
            <SubmitButton pending={withdrawPending} pendingLabel="Withdrawing…" className="button button-danger button-small">
              Withdraw consent
            </SubmitButton>
          </div>
        </form>
      </Dialog>
    </>
  );
}
