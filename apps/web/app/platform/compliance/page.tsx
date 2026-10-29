"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { FormError, PageHeader, Section, StatusBadge } from "@/components/ui";
import type { ApiProblem } from "@/lib/api";
import { apiJson } from "@/lib/fhir";

type Review = {
  review_id: string;
  control_code: string;
  review_status: string;
  due_at: string | null;
};

export default function CompliancePage() {
  const [rows, setRows] = useState<Review[]>([]);
  const [code, setCode] = useState("AC-2");
  const [problem, setProblem] = useState<ApiProblem | null>(null);

  const load = useCallback(async () => {
    const res = await apiJson<Review[]>("/api/v1/platform/compliance/reviews");
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    setRows(res.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    const res = await apiJson("/api/v1/platform/compliance/reviews", {
      method: "POST",
      body: JSON.stringify({ control_code: code }),
    });
    if (!res.ok) {
      setProblem(res.problem);
      return;
    }
    await load();
  }

  return (
    <>
      <PageHeader eyebrow="COMPLIANCE" title="Control reviews" description="Evidence uses secure:// references only." />
      {problem ? <FormError problem={problem} /> : null}
      <Section title="Create review">
        <form className="stack-form" onSubmit={(e) => void onCreate(e)}>
          <label>
            Control code
            <input value={code} onChange={(e) => setCode(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Open review
          </button>
        </form>
      </Section>
      <Section title="Reviews">
        <ul className="dashboard-list">
          {rows.map((row) => (
            <li key={row.review_id}>
              <div className="list-row">
                <div>
                  <strong>{row.control_code}</strong>
                  <p className="muted">Due {row.due_at ?? "n/a"}</p>
                </div>
                <StatusBadge status={row.review_status} />
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
