import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";
import { api, type CaseRecord, type EvidenceRecord } from "@/lib/api";
import { formatBytes, shortHash } from "@/lib/utils";

export function AcquirePage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseId, setCaseId] = useState("");
  const [actor, setActor] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<EvidenceRecord | null>(null);
  const [hints, setHints] = useState<Array<{ vendor: string; confidence: number; markers: string[] }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.listCases().then((data) => {
      setCases(data.cases);
      if (data.cases[0]) setCaseId(data.cases[0].id);
    });
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!caseId || !actor.trim() || !file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.acquire(caseId, actor.trim(), file);
      setResult(response.evidence);
      setHints((response.vendor_hints as Array<{ vendor: string; confidence: number; markers: string[] }>) || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Acquisition failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="label">Acquisition</p>
        <h1 className="font-serif text-3xl text-ink">Image intake</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Upload a bit-for-bit disk image. Pramaan computes SHA-256 at ingest and records the event in custody.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="panel space-y-5 p-6">
        <div className="space-y-2">
          <label className="label" htmlFor="case">Case</label>
          <select id="case" className="field" value={caseId} onChange={(e) => setCaseId(e.target.value)} required>
            <option value="" disabled>Select case</option>
            {cases.map((item) => (
              <option key={item.id} value={item.id}>{item.title}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="label" htmlFor="actor">Custodian</label>
          <input id="actor" className="field" value={actor} onChange={(e) => setActor(e.target.value)} required />
        </div>
        <div className="space-y-2">
          <label className="label" htmlFor="file">Disk image</label>
          <input
            id="file"
            type="file"
            className="field"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
          />
        </div>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <button type="submit" className="btn-primary" disabled={busy}>
          <Upload className="h-4 w-4" />
          {busy ? "Hashing & storing…" : "Acquire evidence"}
        </button>
      </form>

      {result ? (
        <section className="panel p-5">
          <h2 className="text-sm font-medium text-ink">Acquisition record</h2>
          <dl className="mt-4 grid gap-3 text-sm">
            <div className="flex justify-between gap-4"><dt className="text-ink-faint">File</dt><dd>{result.filename}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-ink-faint">Size</dt><dd>{formatBytes(result.size_bytes)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-ink-faint">SHA-256</dt><dd className="mono">{shortHash(result.sha256, 12, 12)}</dd></div>
          </dl>
          {hints.length > 0 ? (
            <div className="mt-4 rounded-lg border border-hairline bg-raised p-3">
              <p className="label">Vendor fingerprint</p>
              <ul className="mt-2 space-y-1 text-sm text-ink-muted">
                {hints.map((h) => (
                  <li key={h.vendor}>{h.vendor} · {(h.confidence * 100).toFixed(0)}% · {h.markers.join(", ")}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <Link className="btn-ghost mt-4 inline-flex" to={`/cases/${result.case_id}`}>View case</Link>
        </section>
      ) : null}
    </div>
  );
}
