import { useEffect, useState } from "react";
import { api, type CaseRecord } from "@/lib/api";

export function ReportPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseId, setCaseId] = useState("");
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.listCases().then((d) => {
      setCases(d.cases);
      if (d.cases[0]) setCaseId(d.cases[0].id);
    });
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void api
      .report(caseId)
      .then((r) => setSummary(r))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load report"));
  }, [caseId]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="label">Reporting</p>
        <h1 className="font-serif text-3xl text-ink">Case report</h1>
        <p className="mt-2 text-sm text-ink-muted">JSON summary with custody chain validation. HTML export for examiner review.</p>
      </div>

      <div className="panel space-y-4 p-5">
        <label className="label" htmlFor="case">Case</label>
        <select id="case" className="field" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
          {cases.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
        {caseId ? (
          <a className="btn-primary inline-flex" href={api.reportHtmlUrl(caseId)} target="_blank" rel="noreferrer">
            Open HTML report
          </a>
        ) : null}
      </div>

      {error ? <p className="text-danger">{error}</p> : null}
      {summary ? (
        <pre className="panel overflow-auto p-4 text-xs text-ink-muted">{JSON.stringify(summary, null, 2)}</pre>
      ) : null}
    </div>
  );
}
