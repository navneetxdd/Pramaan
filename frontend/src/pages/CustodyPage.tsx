import { useEffect, useState } from "react";
import { api, type CaseRecord, type CustodyEvent } from "@/lib/api";

export function CustodyPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseId, setCaseId] = useState("");
  const [events, setEvents] = useState<CustodyEvent[]>([]);
  const [chainOk, setChainOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.listCases().then((data) => {
      setCases(data.cases);
      if (data.cases[0]) setCaseId(data.cases[0].id);
    });
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void api
      .custody(caseId)
      .then((data) => {
        setEvents(data.events);
        setChainOk(data.chain.ok);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load custody"));
  }, [caseId]);

  return (
    <div className="space-y-6">
      <div>
        <p className="label">Chain of custody</p>
        <h1 className="font-serif text-3xl text-ink">Audit ledger</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Append-only events for acquisition, recovery, and verification actions tied to each case.
        </p>
      </div>

      <div className="panel p-5">
        <label className="label" htmlFor="case">Case</label>
        <select id="case" className="field mt-2 max-w-md" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
          {cases.map((item) => (
            <option key={item.id} value={item.id}>{item.title}</option>
          ))}
        </select>
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {chainOk !== null ? (
        <p className={chainOk ? "text-sm text-solved" : "text-sm text-danger"}>
          Custody chain: {chainOk ? "VALID" : "BROKEN"}
        </p>
      ) : null}

      <section className="panel overflow-hidden">
        <div className="border-b border-hairline px-5 py-4">
          <h2 className="text-sm font-medium text-ink">Events</h2>
        </div>
        <ul className="divide-y divide-hairline">
          {events.length === 0 ? (
            <li className="px-5 py-8 text-sm text-ink-faint">No custody events recorded.</li>
          ) : (
            events.map((event) => (
              <li key={event.id} className="grid gap-2 px-5 py-4 md:grid-cols-[180px_1fr_200px]">
                <span className="mono text-ink-faint">{new Date(event.created_at).toLocaleString()}</span>
                <div>
                  <p className="text-sm font-medium text-ink">{event.action.replaceAll("_", " ")}</p>
                  {event.detail ? <p className="mt-1 text-sm text-ink-muted">{event.detail}</p> : null}
                </div>
                <span className="text-sm text-ink-muted">{event.actor}</span>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
