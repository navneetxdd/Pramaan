import { Link } from "react-router-dom";
import { useMemo, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { useCaseContext } from "@/context/CaseContext";
import { api } from "@/lib/api";
import { parseJobStats } from "@/lib/caseStats";
import { useLiveJobs } from "@/hooks/useLiveJobs";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import { toast } from "sonner";
import { waitForJobCompletion } from "@/lib/sse";
import { Database, Layers, AlertTriangle, Activity } from "lucide-react";

type Tab = "active" | "completed" | "all";

export function CaseJobsPage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [tab, setTab] = useState<Tab>("active");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const jobs = workspace?.jobs ?? [];
  const evidence = workspace?.evidence ?? [];
  const live = useLiveJobs(jobs);

  const evidenceName = useMemo(() => {
    const map = new Map(evidence.map((e) => [e.id, e.filename]));
    return (imageId: string) => map.get(imageId) ?? imageId.slice(0, 12);
  }, [evidence]);

  const filtered = useMemo(() => {
    let list = jobs;
    if (tab === "active") list = jobs.filter((j) => j.status === "running" || j.status === "pending");
    if (tab === "completed") list = jobs.filter((j) => j.status === "completed");
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (j) =>
        j.id.toLowerCase().includes(q) ||
        j.vendor?.toLowerCase().includes(q) ||
        evidenceName(j.image_id).toLowerCase().includes(q),
    );
  }, [jobs, tab, query, evidenceName]);

  const activeCount = jobs.filter((j) => j.status === "running" || j.status === "pending").length;
  const failedCount = jobs.filter((j) => j.status === "failed" || j.status === "error").length;
  const parsedVolume = evidence.reduce((s, e) => s + e.size_bytes, 0);
  const artifactTotal = jobs.reduce((s, j) => s + (parseJobStats(j.stats_json).segmentsFound ?? 0), 0);

  async function runRecoveryOnFirst() {
    const device = evidence[0];
    const examiner = workspace?.case.examiner_name;
    if (!device || !examiner) {
      toast.error("Acquire evidence before starting a parsing job");
      return;
    }
    setBusy(true);
    try {
      const started = await api.recover(caseId, device.id, examiner);
      await waitForJobCompletion(started.job.id);
      toast.success("Recovery job completed");
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start job", { duration: Infinity });
    } finally {
      setBusy(false);
    }
  }

  function hashMetric(imageId: string, status: string) {
    if (status === "failed" || status === "error") return { label: "Job failed", tone: "danger" as const };
    const ev = evidence.find((e) => e.id === imageId);
    if (!ev?.sha256) return { label: "Pending verify", tone: "neutral" as const };
    if (status === "completed") return { label: "SHA-256 on file", tone: "success" as const };
    return { label: "In progress", tone: "info" as const };
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Parsing queue</p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">DVR/NVR extraction jobs</h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Recovery and imaging jobs for this case — live progress from the forensic engine.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" className="border-white/20 bg-white/10 text-white hover:bg-white/15" onClick={() => void refresh()}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <Button disabled={busy || evidence.length === 0} onClick={() => void runRecoveryOnFirst()}>
              <Play className="h-4 w-4" />
              Start recovery job
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <DashboardStat label="Active jobs" value={String(activeCount)} icon={Activity} tone="info" />
        <DashboardStat label="Evidence volume" value={formatBytes(parsedVolume)} icon={Database} />
        <DashboardStat label="Artifacts total" value={artifactTotal.toLocaleString()} icon={Layers} />
        <DashboardStat label="Failed jobs" value={String(failedCount).padStart(2, "0")} icon={AlertTriangle} tone={failedCount > 0 ? "danger" : "success"} />
      </div>

      <section className="visily-card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="visily-card-header flex-wrap gap-2">
          <div className="flex gap-1">
            {(["active", "completed", "all"] as Tab[]).map((t) => (
              <button
                key={t}
                type="button"
                className={`rounded px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${
                  tab === t ? "bg-[var(--accent-soft)] text-[var(--accent-500)]" : "text-[var(--text-tertiary)]"
                }`}
                onClick={() => setTab(t)}
              >
                {t === "all" ? "All" : t}
              </button>
            ))}
          </div>
          <input
            className="field mono h-8 max-w-xs flex-1 text-[11px]"
            placeholder="Search by job id or source…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {filtered.length === 0 ? (
            <p className="p-8 text-[13px] text-[var(--text-secondary)]">
              No jobs in this view.{" "}
              <Link to={`/cases/${caseId}/acquire`} className="text-[var(--accent-500)] underline">
                Acquire evidence
              </Link>{" "}
              then run recovery from the Recovery screen.
            </p>
          ) : (
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Source</th>
                  <th>Vendor</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Hash</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((job) => {
                  const liveJob = live[job.id];
                  const progress =
                    liveJob?.progress ??
                    (job.status === "completed" ? 100 : parseJobStats(job.stats_json).progress ?? 0);
                  const metric = hashMetric(job.image_id, liveJob?.status ?? job.status);
                  return (
                    <tr key={job.id}>
                      <td className="mono text-[11px]">{job.id.slice(0, 12)}</td>
                      <td className="max-w-[160px] truncate">{evidenceName(job.image_id)}</td>
                      <td>{job.vendor ?? "—"}</td>
                      <td>
                        <span
                          className={`visily-badge text-[9px] ${
                            job.status === "completed"
                              ? "visily-badge-success"
                              : job.status === "failed" || job.status === "error"
                                ? "visily-badge-danger"
                                : "visily-badge-active"
                          }`}
                        >
                          {liveJob?.status ?? job.status}
                        </span>
                      </td>
                      <td className="min-w-[120px]">
                        <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-4)]">
                          <div className="h-full bg-[var(--accent-500)]" style={{ width: `${Math.min(100, progress)}%` }} />
                        </div>
                        <span className="mono mt-0.5 block text-[10px] text-[var(--text-tertiary)]">{progress.toFixed(0)}%</span>
                      </td>
                      <td>
                        <span
                          className={`text-[10px] font-semibold uppercase ${
                            metric.tone === "success"
                              ? "text-[var(--status-success)]"
                              : metric.tone === "danger"
                                ? "text-[var(--status-danger)]"
                                : "text-[var(--text-tertiary)]"
                          }`}
                        >
                          {metric.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
