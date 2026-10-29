"use client";

import { useMemo, useState } from "react";
import {
  CONSENT_SCOPES,
  DEFAULT_CONSENT_ENABLED,
  activeScopeIds,
  schemaAffectedByConsent,
} from "./consent-scopes";

export type SchemaObject = {
  name: string;
  label?: string;
  purpose: string;
  fields: string[];
  sample?: Record<string, unknown>;
  related?: string[];
};

const DEFAULT_SAMPLES: Record<string, Record<string, unknown>> = {
  ClinicRead: {
    tenant_id: "tn_8f2a…c41",
    display_name: "Northside Family Care",
    slug: "northside-family",
    location_name: "Main Street Clinic",
    timezone: "America/Toronto",
    role: "clinic_admin",
  },
  AppointmentRead: {
    appointment_id: "ap_91c…e2",
    starts_at: "2026-11-04T15:30:00Z",
    ends_at: "2026-11-04T16:00:00Z",
    provider_name: "Dr. Chen",
    location_name: "Main Street Clinic",
    status: "booked",
    timezone: "America/Toronto",
  },
  AvailabilityRead: {
    availability_id: "av_44b…91",
    starts_at: "2026-11-05T14:00:00Z",
    ends_at: "2026-11-05T14:30:00Z",
    provider_name: "Dr. Patel",
    location_id: "loc_main",
    status: "open",
  },
  CredentialRead: {
    credential_id: "cr_12d…88",
    credential_type: "medical_license",
    jurisdiction: "ON",
    regulator: "CPSO",
    status: "pending",
    reviewed_at: null,
  },
  ConsentRead: {
    grant_id: "cg_77a…01",
    purpose: "care_coordination",
    scope: "visit_summary · schedule",
    policy_version: "v2.1",
    granted_at: "2026-10-12T14:22:00Z",
    withdrawn_at: null,
  },
  PatientProfileRead: {
    preferred_name: "Alex Rivera",
    date_of_birth: "1988-04-12",
    phone: "+1-416-555-0142",
    locale: "en-CA",
  },
  InvitationRead: {
    invitation_id: "in_55e…c0",
    invitation_type: "provider",
    expires_at: "2026-11-04T00:00:00Z",
    status: "pending",
  },
  DocumentRead: {
    document_id: "doc_09f…ab",
    document_type: "visit_summary",
    status: "available",
    created_at: "2026-10-20T18:11:00Z",
  },
};

const RELATED: Record<string, string[]> = {
  ClinicRead: ["MemberRead", "LocationRead", "InvitationRead"],
  AppointmentRead: ["AvailabilityRead", "PatientProfileRead", "ConsentRead"],
  AvailabilityRead: ["AppointmentCreate", "CredentialRead"],
  CredentialRead: ["ProviderProfile", "ClinicRead"],
  ConsentRead: ["PatientProfileRead", "DocumentRead", "AppointmentRead"],
  PatientProfileRead: ["ConsentRead", "AppointmentRead"],
  InvitationRead: ["MembershipRead", "ClinicRead"],
  DocumentRead: ["ConsentRead", "PatientProfileRead"],
};

function redact(value: unknown): unknown {
  if (value == null) return value;
  if (typeof value === "string") {
    if (value.includes("@") || value.startsWith("+")) return "••••••••";
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) return "••••-••-••";
    if (value.length <= 4) return "••••";
    return `${value.slice(0, 2)}••••`;
  }
  return "[restricted]";
}

function shapePayload(
  schemaName: string,
  base: Record<string, unknown>,
  enabled: Record<string, boolean>,
): { payload: Record<string, unknown>; withheld: string[] } {
  const scopes = activeScopeIds(enabled);
  const withheld: string[] = [];

  if (schemaName === "ConsentRead") {
    const active = CONSENT_SCOPES.filter((scope) => enabled[scope.id]);
    return {
      payload: {
        ...base,
        scope: active.map((scope) => scope.id).join(" · ") || "(none granted)",
        provision: {
          type: "permit",
          data: active.flatMap((scope) =>
            scope.resources.map((resource) => ({ meaning: "related", reference: { display: resource } })),
          ),
        },
        meta: {
          privacy_in_payload: true,
          active_scopes: scopes,
          interactive_demo: true,
        },
      },
      withheld: CONSENT_SCOPES.filter((scope) => !enabled[scope.id]).map((scope) => scope.id),
    };
  }

  const payload: Record<string, unknown> = { ...base };
  payload._consent = { active_scopes: scopes, interactive_demo: true };

  if (schemaName === "AppointmentRead" || schemaName === "AvailabilityRead") {
    if (!enabled.schedule) {
      for (const field of ["starts_at", "ends_at", "provider_name", "location_name", "timezone"]) {
        if (field in payload) {
          payload[field] = redact(payload[field]);
          withheld.push(field);
        }
      }
      payload.status = "restricted";
      withheld.push("status");
    }
  }

  if (schemaName === "PatientProfileRead") {
    if (!enabled.schedule) {
      payload.phone = redact(payload.phone);
      withheld.push("phone");
    }
    if (!enabled.visit_summary) {
      payload.preferred_name = redact(payload.preferred_name);
      payload.date_of_birth = redact(payload.date_of_birth);
      withheld.push("preferred_name", "date_of_birth");
    }
    if (!enabled.meds) {
      payload.medications = { status: "restricted", reason: "meds scope off" };
      withheld.push("medications");
    } else {
      payload.medications = { status: "planned", items: ["(pharmacy edge — not live)"] };
    }
  }

  if (schemaName === "DocumentRead") {
    const allowed =
      (payload.document_type === "visit_summary" && enabled.visit_summary) ||
      (String(payload.document_type).includes("lab") && enabled.lab_history) ||
      (enabled.visit_summary && enabled.lab_history);
    if (!allowed && !enabled.visit_summary && !enabled.lab_history) {
      payload.document_type = "[restricted]";
      payload.status = "withheld";
      payload.created_at = redact(payload.created_at);
      withheld.push("document_type", "status", "created_at");
    } else if (payload.document_type === "visit_summary" && !enabled.visit_summary) {
      payload.status = "withheld";
      payload.preview = null;
      withheld.push("status", "preview");
    } else if (!enabled.lab_history && String(payload.document_type).includes("lab")) {
      payload.status = "withheld";
      withheld.push("status");
    }
  }

  return { payload, withheld };
}

function inferTsType(value: unknown): string {
  if (value === null) return "string | null";
  if (Array.isArray(value)) return "string[]";
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "object") return "Record<string, unknown>";
  return "string";
}

function toTypeScript(name: string, payload: Record<string, unknown>, fields: string[]): string {
  const keys = Array.from(new Set([...fields, ...Object.keys(payload).filter((key) => !key.startsWith("_"))]));
  const lines = keys.map((field) => {
    const value = payload[field];
    if (value === undefined) return `  // ${field}: withheld by consent`;
    return `  ${field}: ${inferTsType(value)};`;
  });
  if (payload._consent) {
    lines.push(`  // _consent omitted from public contract — demo metadata only`);
  }
  return [`export type ${name} = {`, ...lines, `};`].join("\n");
}

export function SchemaInspector({ objects }: { objects: SchemaObject[] }) {
  const [selected, setSelected] = useState(objects[0]?.name ?? "");
  const [view, setView] = useState<"json" | "typescript">("json");
  const [enabled, setEnabled] = useState<Record<string, boolean>>(DEFAULT_CONSENT_ENABLED);

  const current = useMemo(
    () => objects.find((object) => object.name === selected) ?? objects[0],
    [objects, selected],
  );

  const shaped = useMemo(() => {
    if (!current) return null;
    const base = current.sample ?? DEFAULT_SAMPLES[current.name] ?? Object.fromEntries(current.fields.map((f) => [f, "…"]));
    if (!schemaAffectedByConsent(current.name)) {
      return { payload: base, withheld: [] as string[] };
    }
    return shapePayload(current.name, base, enabled);
  }, [current, enabled]);

  if (!current || !shaped) return null;

  const related = current.related ?? RELATED[current.name] ?? [];
  const consentInteractive = schemaAffectedByConsent(current.name);
  const jsonText = JSON.stringify(shaped.payload, null, 2);
  const tsText = toTypeScript(current.name, shaped.payload, current.fields);
  const relevantScopes = CONSENT_SCOPES.filter(
    (scope) => scope.affects.includes(current.name) || current.name === "ConsentRead",
  );

  return (
    <div className="schema-inspector">
      <div className="schema-inspector-list" role="listbox" aria-label="API schemas">
        <p className="schema-inspector-hint">
          Select a schema, switch JSON / TypeScript, and toggle consent scopes to watch the sample payload change live.
        </p>
        {objects.map((object) => (
          <button
            key={object.name}
            type="button"
            role="option"
            aria-selected={object.name === current.name}
            className={`schema-inspector-item${object.name === current.name ? " is-selected" : ""}`}
            onClick={() => setSelected(object.name)}
          >
            <strong>{object.label ?? object.name}</strong>
            <code>{object.name}</code>
            <span>{object.purpose}</span>
            {schemaAffectedByConsent(object.name) ? (
              <em className="schema-consent-tag">Consent-sensitive</em>
            ) : null}
          </button>
        ))}
      </div>
      <div className="schema-inspector-panel" aria-live="polite">
        <header className="schema-inspector-head">
          <div>
            <p className="section-kicker">Interactive payload · synthetic demo</p>
            <h3>
              {current.label ? <span>{current.label} · </span> : null}
              <code>{current.name}</code>
            </h3>
            <p>{current.purpose}</p>
          </div>
          <div className="schema-view-toggle" role="group" aria-label="Payload format">
            <button type="button" className={view === "json" ? "is-active" : ""} onClick={() => setView("json")}>
              JSON
            </button>
            <button
              type="button"
              className={view === "typescript" ? "is-active" : ""}
              onClick={() => setView("typescript")}
            >
              TypeScript
            </button>
          </div>
        </header>

        {consentInteractive ? (
          <div className="schema-consent-lab">
            <div className="schema-consent-lab-head">
              <p className="schema-relations-label">Consent scopes</p>
              <p className="muted">
                Toggle scopes to trim fields in the {view === "json" ? "JSON" : "TypeScript"} view. Restricted values stay
                marked—never presented as live PHI.
              </p>
            </div>
            <ul className="schema-consent-toggles">
              {relevantScopes.map((scope) => (
                <li key={scope.id}>
                  <label className={`schema-consent-toggle${enabled[scope.id] ? " is-on" : ""}`}>
                    <input
                      type="checkbox"
                      checked={Boolean(enabled[scope.id])}
                      onChange={(event) =>
                        setEnabled((currentScopes) => ({
                          ...currentScopes,
                          [scope.id]: event.target.checked,
                        }))
                      }
                    />
                    <span>
                      <strong>{scope.label}</strong>
                      <em>{scope.detail}</em>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            {shaped.withheld.length ? (
              <p className="schema-consent-withheld" role="status">
                Currently withheld or redacted: {shaped.withheld.join(", ")}
              </p>
            ) : (
              <p className="schema-consent-withheld is-clear" role="status">
                No fields withheld for the active scopes.
              </p>
            )}
          </div>
        ) : (
          <p className="schema-consent-note muted">
            This schema is not consent-scoped. Select Consent, Appointment, Document, or Patient Profile to test live
            payload trimming.
          </p>
        )}

        <pre className={`schema-payload${consentInteractive ? " is-interactive" : ""}`} tabIndex={0}>
          <code>{view === "json" ? jsonText : tsText}</code>
        </pre>

        <div className="schema-relations">
          <p className="schema-relations-label">Related objects</p>
          <ul>
            {related.map((name) => (
              <li key={name}>
                {objects.some((o) => o.name === name) ? (
                  <button type="button" onClick={() => setSelected(name)}>
                    <code>{name}</code>
                  </button>
                ) : (
                  <code>{name}</code>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
