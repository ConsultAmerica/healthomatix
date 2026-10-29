"use client";

import { useCallback, useEffect, useState } from "react";
import { FormError, Notice, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Overview = {
  agents: number;
  enabled_agents: number;
  runs: number;
  pending_approvals: number;
  open_safety_events: number;
  estimated_cost_cents: number;
  note: string;
};

type Agent = {
  agent_id: string;
  agent_code: string;
  agent_name: string;
  domain: string;
  risk_level: string;
  current_version: string;
  enabled: boolean;
  description: string;
};

type Tool = {
  tool_id: string;
  tool_code: string;
  risk_level: string;
  required_permission: string;
  approval_required: boolean;
  enabled: boolean;
};

type SafetyEvent = {
  event_id: string;
  event_type: string;
  severity: string;
  status: string;
  summary: string;
};

type Usage = {
  usage_events: number;
  estimated_cost_cents: number;
  note: string;
};

type Evaluation = {
  evaluation_id: string;
  evaluation_type: string;
  dataset_version: string;
  status: string;
};

export default function AiCommandCenterPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [safety, setSafety] = useState<SafetyEvent[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [evals, setEvals] = useState<Evaluation[]>([]);
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    setProblem(null);
    const [o, a, t, s, u, e] = await Promise.all([
      apiJson<Overview>("/api/v1/platform/ai/governance/overview"),
      apiJson<Agent[]>("/api/v1/platform/ai/agents"),
      apiJson<Tool[]>("/api/v1/platform/ai/tools"),
      apiJson<SafetyEvent[]>("/api/v1/platform/ai/safety-events"),
      apiJson<Usage>("/api/v1/platform/ai/usage"),
      apiJson<Evaluation[]>("/api/v1/platform/ai/evaluations"),
    ]);
    for (const res of [o, a, t, s, u, e]) {
      if (!res.ok) {
        setProblem(res.problem);
        return;
      }
    }
    setOverview(o.data as Overview);
    setAgents(a.data as Agent[]);
    setTools(t.data as Tool[]);
    setSafety(s.data as SafetyEvent[]);
    setUsage(u.data as Usage);
    setEvals(e.data as Evaluation[]);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="ENTERPRISE AI"
        title="AI command center"
        description="Registered agents, tool gateway posture, approvals backlog, safety events, and sandbox cost."
        actions={
          <button className="button button-small button-light" type="button" onClick={() => void load()}>
            Refresh
          </button>
        }
      />

      <Notice title="Governed orchestration only" tone="info">
        Agents produce reviewable proposals. Clinical signing, claim submission, refunds, and PHI disclosure
        remain human-authorized. Fake models are default — no production agent automation without approval.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      {overview ? (
        <div className="stat-grid workboard-stats">
          <div className="stat-tile">
            <span className="stat-label">agents</span>
            <strong className="stat-value">{overview.enabled_agents}/{overview.agents}</strong>
          </div>
          <div className="stat-tile">
            <span className="stat-label">runs</span>
            <strong className="stat-value">{overview.runs}</strong>
          </div>
          <div className="stat-tile">
            <span className="stat-label">pending approvals</span>
            <strong className="stat-value">{overview.pending_approvals}</strong>
          </div>
          <div className="stat-tile">
            <span className="stat-label">open safety</span>
            <strong className="stat-value">{overview.open_safety_events}</strong>
          </div>
          <div className="stat-tile">
            <span className="stat-label">est. cost (¢)</span>
            <strong className="stat-value">{overview.estimated_cost_cents}</strong>
          </div>
        </div>
      ) : null}

      <Section title="Agent registry">
        {agents.length === 0 ? (
          <p className="muted">No agents loaded.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Domain</th>
                <th>Version</th>
                <th>Risk</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.agent_id}>
                  <td>
                    <strong>{agent.agent_name}</strong>
                    <div className="muted">{agent.agent_code}</div>
                  </td>
                  <td>{agent.domain}</td>
                  <td>{agent.current_version}</td>
                  <td>{agent.risk_level}</td>
                  <td>
                    <StatusBadge status={agent.enabled ? "active" : "disabled"}>
                      {agent.enabled ? "enabled" : "disabled"}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Tool gateway">
        <table className="data-table">
          <thead>
            <tr>
              <th>Tool</th>
              <th>Risk</th>
              <th>Permission</th>
              <th>Approval</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((tool) => (
              <tr key={tool.tool_id}>
                <td>{tool.tool_code}</td>
                <td>{tool.risk_level}</td>
                <td>{tool.required_permission}</td>
                <td>{tool.approval_required ? "required" : "optional"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Safety events">
        {safety.length === 0 ? (
          <p className="muted">No open safety events recorded.</p>
        ) : (
          <ul className="dashboard-list">
            {safety.map((event) => (
              <li key={event.event_id}>
                <StatusBadge status={event.severity}>{event.severity}</StatusBadge>{" "}
                <strong>{event.event_type}</strong> — {event.summary}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Evaluations">
        {evals.length === 0 ? (
          <p className="muted">No agent evaluations recorded yet.</p>
        ) : (
          <ul className="dashboard-list">
            {evals.map((row) => (
              <li key={row.evaluation_id}>
                {row.evaluation_type} · {row.dataset_version} · {row.status}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {usage ? (
        <Section title="Usage & cost">
          <p>
            {usage.usage_events} metered events · {usage.estimated_cost_cents}¢ estimated. {usage.note}
          </p>
        </Section>
      ) : null}
    </>
  );
}
