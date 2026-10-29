"use client";

import { useMemo, useState } from "react";
import {
  CONSENT_SCOPES,
  DEFAULT_CONSENT_ENABLED,
  activeScopeIds,
} from "./consent-scopes";

export function ConsentScopePreview() {
  const [enabled, setEnabled] = useState<Record<string, boolean>>(DEFAULT_CONSENT_ENABLED);
  const [view, setView] = useState<"json" | "typescript">("json");

  const payload = useMemo(() => {
    const active = CONSENT_SCOPES.filter((scope) => enabled[scope.id]);
    return {
      resourceType: "Consent",
      status: "active",
      scope: activeScopeIds(enabled),
      provision: {
        type: "permit",
        data: active.flatMap((scope) =>
          scope.resources.map((resource) => ({ meaning: "related", reference: { display: resource } })),
        ),
      },
      meta: { privacy_in_payload: true, interactive_demo: true },
    };
  }, [enabled]);

  const jsonText = JSON.stringify(payload, null, 2);
  const tsText = [
    "export type ConsentRead = {",
    '  resourceType: "Consent";',
    '  status: "active" | "rejected" | "inactive";',
    "  scope: string[];",
    "  provision: {",
    '    type: "permit" | "deny";',
    "    data: Array<{ meaning: string; reference: { display: string } }>;",
    "  };",
    "  meta: { privacy_in_payload: boolean; interactive_demo?: boolean };",
    "};",
    "",
    `// Active scopes in this preview: ${payload.scope.join(", ") || "(none)"}`,
    `// Provision entries: ${payload.provision.data.length}`,
  ].join("\n");

  return (
    <div className="consent-scope-preview">
      <div className="consent-scope-toggles">
        <p className="section-kicker">ConsentRead scopes</p>
        <h3>Privacy in the payload</h3>
        <p>Toggle what a care team could receive. Restricted scopes disappear from the sample Consent resource.</p>
        <ul>
          {CONSENT_SCOPES.map((scope) => (
            <li key={scope.id}>
              <label className="consent-scope-row">
                <input
                  type="checkbox"
                  checked={Boolean(enabled[scope.id])}
                  onChange={(event) =>
                    setEnabled((current) => ({ ...current, [scope.id]: event.target.checked }))
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
      </div>
      <div className="consent-scope-output">
        <div className="schema-view-toggle" role="group" aria-label="Consent payload format">
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
        <pre className="schema-payload consent-scope-payload" tabIndex={0} aria-live="polite">
          <code>{view === "json" ? jsonText : tsText}</code>
        </pre>
      </div>
    </div>
  );
}
