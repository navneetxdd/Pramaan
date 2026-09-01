import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download } from "lucide-react";
import { api, type RecoveryJob, type Segment } from "@/lib/api";
import { formatBytes, formatOffset } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";

export function AnalyzePage() {
  const [params] = useSearchParams();
  const jobId = params.get("job") ?? "";
  const [job, setJob] = useState<RecoveryJob | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    void api
      .getJob(jobId)
      .then((data) => {
        setJob(data.job);
        setSegments(data.segments);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load job"));
  }, [jobId]);

  const totalBytes = useMemo(
    () => segments.reduce((sum, seg) => sum + (seg.offset_end - seg.offset_start), 0),
    [segments],
  );

  async function handleExport(segmentId: string) {
    if (!jobId) return;
    setExporting(segmentId);
    try {
      const result = await api.exportSegment(jobId, segmentId);
      window.open(result.download_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  if (!jobId) {
    return (
      <div className="panel p-8 text-center">
        <p className="text-sm text-ink-muted">Select a recovery job from Recover or a case detail view.</p>
      </div>
    );
  }

  if (error) return <p className="text-danger">{error}</p>;
  if (!job) return <p className="text-ink-faint">Loading timeline…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label">Analysis</p>
          <h1 className="font-serif text-3xl text-ink">Segment timeline</h1>
          <p className="mono mt-2">{job.vendor || "Unknown vendor"} · {job.adapter || "—"}</p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="panel p-4"><p className="label">Segments</p><p className="mt-2 text-2xl font-medium">{segments.length}</p></div>
        <div className="panel p-4"><p className="label">Recovered bytes</p><p className="mt-2 text-2xl font-medium">{formatBytes(totalBytes)}</p></div>
        <div className="panel p-4"><p className="label">Validation</p><p className="mt-2 text-sm text-ink-muted">Dual-signature DHAV · HKVI blocks · NAL fallback</p></div>
      </div>

      <section className="panel overflow-hidden">
        <div className="border-b border-hairline px-5 py-4">
          <h2 className="text-sm font-medium text-ink">Offset index</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-hairline bg-raised text-xs uppercase tracking-wide text-ink-faint">
              <tr>
                <th className="px-5 py-3">Channel</th>
                <th className="px-5 py-3">Start</th>
                <th className="px-5 py-3">End</th>
                <th className="px-5 py-3">Size</th>
                <th className="px-5 py-3">Confidence</th>
                <th className="px-5 py-3">Validation</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {segments.map((seg) => (
                <tr key={seg.id} className="border-b border-hairline last:border-0">
                  <td className="px-5 py-3">{seg.channel ?? "—"}</td>
                  <td className="mono px-5 py-3">{formatOffset(seg.offset_start)}</td>
                  <td className="mono px-5 py-3">{formatOffset(seg.offset_end)}</td>
                  <td className="px-5 py-3">{formatBytes(seg.offset_end - seg.offset_start)}</td>
                  <td className="px-5 py-3">{(seg.confidence * 100).toFixed(0)}%</td>
                  <td className="px-5 py-3">{seg.validation}</td>
                  <td className="px-5 py-3">
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={exporting === seg.id}
                      onClick={() => void handleExport(seg.id)}
                    >
                      <Download className="h-4 w-4" />
                      {exporting === seg.id ? "…" : "Export"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
