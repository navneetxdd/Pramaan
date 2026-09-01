import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ScanSearch } from "lucide-react";
import { api, type CaseRecord, type EvidenceRecord } from "@/lib/api";

export function RecoverPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseId, setCaseId] = useState("");
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([]);
  const [imageId, setImageId] = useState("");
  const [actor, setActor] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [segmentCount, setSegmentCount] = useState(0);

  useEffect(() => {
    void api.listCases().then((data) => {
      setCases(data.cases);
      if (data.cases[0]) setCaseId(data.cases[0].id);
    });
  }, []);

  useEffect(() => {
    if (!caseId) return;
    void api.getCase(caseId).then((data) => {
      setEvidence(data.evidence);
      if (data.evidence[0]) setImageId(data.evidence[0].id);
    });
  }, [caseId]);

  async function handleRecover(event: React.FormEvent) {
    event.preventDefault();
    if (!caseId || !imageId || !actor.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await api.recover(caseId, imageId, actor.trim());
      setJobId(data.job.id);
      setSegmentCount(data.segments.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Recovery failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="label">Recovery</p>
        <h1 className="font-serif text-3xl text-ink">Vendor-aware carve</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Detects Dahua DHAV, Hikvision HKVI, or falls back to H.264 NAL carving. Output is offset-indexed for timeline review.
        </p>
      </div>

      <form onSubmit={handleRecover} className="panel space-y-5 p-6">
        <div className="space-y-2">
          <label className="label" htmlFor="case">Case</label>
          <select id="case" className="field" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
            {cases.map((item) => (
              <option key={item.id} value={item.id}>{item.title}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="label" htmlFor="image">Evidence image</label>
          <select id="image" className="field" value={imageId} onChange={(e) => setImageId(e.target.value)}>
            {evidence.length === 0 ? <option value="">No images</option> : null}
            {evidence.map((item) => (
              <option key={item.id} value={item.id}>{item.filename}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="label" htmlFor="actor">Operator</label>
          <input id="actor" className="field" value={actor} onChange={(e) => setActor(e.target.value)} required />
        </div>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <button type="submit" className="btn-primary" disabled={busy || !imageId}>
          <ScanSearch className="h-4 w-4" />
          {busy ? "Scanning image…" : "Run recovery"}
        </button>
      </form>

      {jobId ? (
        <section className="panel p-5">
          <h2 className="text-sm font-medium text-ink">Recovery complete</h2>
          <p className="mt-2 text-sm text-ink-muted">{segmentCount} segments indexed.</p>
          <Link className="btn-ghost mt-4 inline-flex" to={`/analyze?job=${jobId}`}>Open timeline</Link>
        </section>
      ) : null}
    </div>
  );
}
