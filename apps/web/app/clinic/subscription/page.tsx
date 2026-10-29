"use client";

import { useCallback, useEffect, useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Entitlement = { feature_code: string; enabled: boolean; limit_value?: number | null };
type Subscription = {
  subscription_id: string;
  plan_code: string;
  status: string;
  payment_provider_reference: string;
};

export default function SubscriptionPage() {
  return (
    <RoleGate roles={["tenant_admin"]}>
      <SubscriptionWorkspace />
    </RoleGate>
  );
}

function SubscriptionWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    const result = await apiJson<Entitlement[]>(`/api/v1/tenants/${tenant_id}/entitlements`);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setEntitlements(result.data);
  }, [tenant_id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function activate(planCode: string) {
    setPending(true);
    setProblem(null);
    const result = await apiJson<Subscription>(
      `/api/v1/tenants/${tenant_id}/subscriptions/activate`,
      { method: "POST", body: JSON.stringify({ plan_code: planCode }) },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setSubscription(result.data);
    await load();
  }

  return (
    <>
      <PageHeader
        eyebrow="SAAS"
        title="Healthomatix subscription"
        description={`${tenant_name} · platform billing is separate from patient/insurance payments.`}
      />

      <Notice title="Separate billing domains">
        Clinic subscription charges never mix with patient balances or insurance remittances. Sandbox
        checkout uses FakeSaaSBillingAdapter — no card data stored.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Activate sandbox plan">
        <div className="row-actions">
          <button className="button button-light" type="button" disabled={pending} onClick={() => void activate("starter")}>
            Starter
          </button>
          <button className="button" type="button" disabled={pending} onClick={() => void activate("professional")}>
            Professional (includes RCM)
          </button>
          <button className="button button-light" type="button" disabled={pending} onClick={() => void activate("enterprise")}>
            Enterprise
          </button>
        </div>
        {subscription ? (
          <p className="muted" style={{ marginTop: 12 }}>
            {subscription.plan_code} · <StatusBadge status={subscription.status} /> ·{" "}
            {subscription.payment_provider_reference}
          </p>
        ) : null}
      </Section>

      <Section title="Feature entitlements (backend enforced)">
        {entitlements.length ? (
          <ul className="dashboard-list">
            {entitlements.map((item) => (
              <li key={item.feature_code}>
                <div>
                  <strong>{item.feature_code}</strong>
                  <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No entitlements yet — activate a plan.</p>
        )}
      </Section>
    </>
  );
}
