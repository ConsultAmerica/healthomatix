"use client";

import Link from "next/link";
import { useState } from "react";
import { useActiveMembership } from "@/components/portal/portal-context";
import { FormError, Notice, PageHeader, Section } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type EducationAnswer = {
  education_id: string;
  topic: string;
  question: string;
  answer: string;
  source_references: Array<{
    title?: string;
    source_id?: string;
    version?: string;
    passage?: string;
  }>;
  escalated: boolean;
  status: string;
};

export default function PatientEducationPage() {
  const { tenant_id, tenant_name } = useActiveMembership();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<EducationAnswer | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [pending, setPending] = useState(false);

  async function ask() {
    if (!question.trim()) return;
    setPending(true);
    setProblem(null);
    const result = await apiJson<EducationAnswer>(
      `/api/v1/tenants/${tenant_id}/patient-education/questions`,
      { method: "POST", body: JSON.stringify({ question: question.trim() }) },
    );
    setPending(false);
    if (!result.ok) {
      setProblem(result.problem);
      return;
    }
    setAnswer(result.data);
  }

  return (
    <>
      <PageHeader
        eyebrow="EDUCATION"
        title="Patient education assistant"
        description={`${tenant_name} · source-grounded general explanations — not personalized medical advice.`}
        actions={
          <Link className="button button-small button-light" href="/patient/messages">
            Message clinic
          </Link>
        }
      />

      <Notice title="Safety" tone="warning">
        This assistant does not diagnose, prescribe, or replace your clinician. Portal messaging is
        not for emergencies—call emergency services if you need urgent care.
      </Notice>

      {problem ? <FormError problem={problem} /> : null}

      <Section title="Ask a question">
        <form
          className="stack-form"
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
        >
          <label className="field">
            Question
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. What is HbA1c?"
              required
            />
          </label>
          <button className="button" type="submit" disabled={pending}>
            {pending ? "Thinking…" : "Get educational answer"}
          </button>
        </form>
      </Section>

      {answer ? (
        <Section title={answer.escalated ? "Escalation guidance" : answer.topic}>
          <p>{answer.answer}</p>
          {answer.escalated ? (
            <Notice title="Human review recommended">
              For personal medical advice,{" "}
              <Link href="/patient/messages">message your care team</Link>.
            </Notice>
          ) : null}
          <ul className="dashboard-list" style={{ marginTop: 12 }}>
            {answer.source_references.map((source, index) => (
              <li key={`${source.source_id || "src"}-${index}`}>
                <div>
                  <strong>{source.title || source.source_id || "Source"}</strong>
                  <span className="muted">
                    {[source.source_id, source.version && `v${source.version}`, source.passage]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}
