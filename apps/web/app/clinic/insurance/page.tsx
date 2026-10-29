"use client";

import { useState } from "react";
import { RoleGate } from "@/components/portal/portal-shell";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section, StatusBadge, TextField } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Payer = { payer_id: string; name: string; payer_identifier: string };
type Policy = {
  policy_id: string;
  plan_name: string;
  member_identifier: string;
  coverage_order: number;
  status: string;
};
type Eligibility = {
  coverage_status: string;
  financial_readiness: string;
  disclaimer: string;
  benefits_summary: Record<string, unknown>;
};

export default function InsurancePage() {
  return (
    <RoleGate roles={["tenant_admin", "staff", "provider"]}>
      <InsuranceWorkspace />
    </RoleGate>
  );
}

function InsuranceWorkspace() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [patientId, setPatientId] = useState("");
  const [memberId, setMemberId] = useState("");
  const [planName, setPlanName] = useState("Sandbox PPO");
  const [payer, setPayer] = useState<Payer | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);

  async function seedPayerAndPolicy() {
    if (!patientId.trim() || !memberId.trim()) return;
    setPending(true);
    setProblem(null);
    const payerRes = await apiJson<Payer>(`/api/v1/tenants/${tenant_id}/insurance/payers`, {
      method: "POST",
      body: JSON.stringify({ name: "Sandbox Health Plan", payer_identifier: "SANDBOX-HP" }),
    });
    if (!payerRes.ok) {
      setPending(false);
      setProblem(payerRes.problem);
      return;
    }
    setPayer(payerRes.data);
    const policyRes = await apiJson<Policy>(
      `/api/v1/tenants/${tenant_id}/patients/${patientId.trim()}/insurance`,
      {
        method: "POST",
        body: JSON.stringify({
          patient_id: patientId.trim(),
          payer_id: payerRes.data.payer_id,
          member_identifier: memberId.trim(),
          plan_name: planName,
          coverage_order: 1,
        }),
      },
    );
    setPending(false);
    if (!policyRes.ok) {
      setProblem(policyRes.problem);
      return;
    }
    setPolicy(policyRes.data);
  }

  async function verify() {
    if (!policy) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<Eligibility>(
      `/api/v1/tenants/${tenant_id}/insurance/policies/${policy.policy_id}/verify-eligibility`,
      { method: "POST", body: "{}" },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setEligibility(result.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="INSURANCE"
        title="Coverage & eligibility"
        description={`${tenant_name} · synthetic policies and sandbox 270/271 verification.`}
      />

      <Notice title="Not a payment guarantee" tone="warning">
        Coverage responses are sandbox demonstrations. Member IDs are masked in API reads. Ending a
        member ID with INACTIVE or 0000 simulates inactive coverage.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Add sandbox policy">
        <div className="stack-form">
          <TextField
            label="Patient user ID"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
          />
          <TextField
            label="Member ID"
            value={memberId}
            onChange={(e) => setMemberId(e.target.value)}
          />
          <TextField label="Plan name" value={planName} onChange={(e) => setPlanName(e.target.value)} />
          <div className="row-actions">
            <button
              className="button"
              type="button"
              disabled={pending}
              onClick={() => void seedPayerAndPolicy()}
            >
              Save policy
            </button>
            {policy ? (
              <button className="button button-light" type="button" disabled={pending} onClick={() => void verify()}>
                Verify eligibility
              </button>
            ) : null}
          </div>
        </div>
        {payer ? (
          <p className="muted" style={{ marginTop: 8 }}>
            Payer {payer.name} · {payer.payer_identifier}
          </p>
        ) : null}
        {policy ? (
          <p className="muted">
            Policy {policy.plan_name} · member {policy.member_identifier} · order{" "}
            {policy.coverage_order} · <StatusBadge status={policy.status} />
          </p>
        ) : null}
      </Section>

      {eligibility ? (
        <Section title="Eligibility response">
          <p>
            Coverage <StatusBadge status={eligibility.coverage_status} /> · readiness{" "}
            <StatusBadge status={eligibility.financial_readiness} />
          </p>
          <p className="muted">{eligibility.disclaimer}</p>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              fontSize: "0.8rem",
              maxHeight: 200,
              overflow: "auto",
            }}
          >
            {JSON.stringify(eligibility.benefits_summary, null, 2)}
          </pre>
        </Section>
      ) : null}
    </>
  );
}
