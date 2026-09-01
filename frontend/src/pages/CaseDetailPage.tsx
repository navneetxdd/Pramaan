import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type CaseRecord, type CustodyEvent, type EvidenceRecord, type RecoveryJob } from "@/lib/api";
import { formatBytes, shortHash } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";

export function CaseDetailPage() {
  const { caseId } = useParams();
  const [caseRecord, setCaseRecord] = useState<CaseRecord | null>(null);
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([]);
  const [jobs, setJobs] = useState<RecoveryJob[]>([]);
  const [custody, setCustody] = useState<CustodyEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId) return;
    void api
      .getCase(caseId)
      .then((data) => {
        setCaseRecord(data.case);
        setEvidence(data.evidence);
        setJobs(data.jobs);
        setCustody(data.custody);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load case"));
  }, [caseId]);

  if (!caseId) return null;
  if (error) return <p className="text-danger">{error}</p>;
  if (!caseRecord) return <p className="text-ink-faint">Loading case…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/" className="text-xs text-ink-faint hover:text-ink">← Cases</Link>
          <h1 className="mt-2 font-serif text-3xl text-ink">{caseRecord.title}</h1>
          <p className="mono mt-2">{caseRecord.examiner} · {caseRecord.reference || "No reference"}</p>
        </div>
        <StatusBadge status={caseRecord.status} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="text-sm font-medium text-ink">Evidence images</h2>
          <ul className="mt-4 space-y-3">
            {evidence.length === 0 ? (
              <li className="text-sm text-ink-faint">No images acquired.</li>
            ) : (
              evidence.map((item) => (
                <li key={item.id} className="rounded-lg border border-hairline bg-raised p-3">
                  <p className="text-sm font-medium text-ink">{item.filename}</p>
                  <p className="mono mt-1">{shortHash(item.sha256)} · {formatBytes(item.size_bytes)}</p>
                </li>
              ))
            )}
          </ul>
        </section>

        <section className="panel p-5">
          <h2 className="text-sm font-medium text-ink">Recovery jobs</h2>
          <ul className="mt-4 space-y-3">
            {jobs.length === 0 ? (
              <li className="text-sm text-ink-faint">No recovery runs yet.</li>
            ) : (
              jobs.map((job) => (
                <li key={job.id} className="flex items-center justify-between rounded-lg border border-hairline bg-raised p-3">
                  <div>
                    <p className="mono">{job.id.slice(0, 12)}…</p>
                    <p className="mt-1 text-xs text-ink-faint">{job.vendor || "—"} · {job.adapter || "—"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={job.status} />
                    <Link className="btn-ghost" to={`/analyze?job=${job.id}`}>Open</Link>
                  </div>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>

      <section className="panel p-5">
        <h2 className="text-sm font-medium text-ink">Recent custody</h2>
        <ul className="mt-4 space-y-2">
          {custody.slice(0, 8).map((event) => (
            <li key={event.id} className="flex flex-wrap items-baseline justify-between gap-2 border-b border-hairline py-2 last:border-0">
              <span className="text-sm text-ink">{event.action.replaceAll("_", " ")}</span>
              <span className="mono">{event.actor} · {new Date(event.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
