import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HardDrive, ScanSearch, Shield } from "lucide-react";
import { useCaseContext } from "@/context/CaseContext";
import { api } from "@/lib/api";
import { HeroBanner } from "@/components/visily/HeroBanner";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { JobProgressCard } from "@/components/visily/JobProgressCard";
import { IntegrityPanel } from "@/components/visily/IntegrityPanel";
import { AuditLogPanel } from "@/components/visily/AuditLogPanel";
import { EvidenceTile } from "@/components/visily/EvidenceTile";
import type { ChainLinkState } from "@/components/forensic/ChainLinkIndicator";
import {
  failedJobCount,
  jobDisplayProgress,
  parseJobStats,
  runningJobs,
  totalRecoveredSegments,
} from "@/lib/caseStats";
import { formatBytes } from "@/lib/utils";
import { integrityLabel, resolveIntegrityState } from "@/lib/integrity";

export function CaseOverviewPage() {
  const { caseId, workspace } = useCaseContext();
  const [custody, setCustody] = useState<ChainLinkState>("checking");
  const [chainTip, setChainTip] = useState<string | null>(null);
  const [liveJobState, setLiveJobState] = useState<
    Record<string, { progress: number; message: string }>
  >({});

  useEffect(() => {
    void api
      .custodyStatus(caseId)
      .then((s) => {
        setCustody(s.intact ? "intact" : "broken");
        setChainTip(s.tip_hash ?? null);
      })
      .catch(() => setCustody("unknown"));
  }, [caseId]);

  useEffect(() => {
    if (!workspace) return;
    const active = runningJobs(workspace.jobs);
    if (active.length === 0) return;

    let cancelled = false;
    async function poll() {
      const next: Record<string, { progress: number; message: string }> = {};
      for (const job of active) {
        try {
          const status = await api.getJobStatus(job.id);
          next[job.id] = {
            progress: typeof status.progress === "number" ? status.progress : 0,
            message: status.message ?? job.error ?? job.status,
          };
        } catch {
          next[job.id] = { progress: 0, message: job.status };
        }
      }
      if (!cancelled) setLiveJobState(next);
    }
    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workspace]);

  if (!workspace) return null;

  const { case: record, evidence, jobs, custody: events } = workspace;
  const totalBytes = evidence.reduce((sum, e) => sum + e.size_bytes, 0);
  const segmentTotal = totalRecoveredSegments(jobs);
  const flagged = failedJobCount(jobs);
  const identified = evidence.filter(
    (e) => e.identification?.recommended_adapter,
  ).length;
  const coveragePct =
    evidence.length === 0
      ? "—"
      : `${Math.round((identified / evidence.length) * 100)}%`;
  const sortedJobs = jobs
    .filter((j) => j.kind === "recovery")
    .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));

  return (
    <div className="mx-auto flex max-w-[1440px] flex-col gap-4">
      <HeroBanner
        badge={record.status === "closed" ? "Closed case" : "Open case"}
        since={`Opened ${new Date(record.created_at).toLocaleString()}`}
        title={record.name}
        description={record.notes?.trim() || "No case notes."}
        meta={[
          { label: "Case handler", value: record.examiner_name },
          { label: "Case ID", value: record.id.slice(0, 18) },
        ]}
        primaryAction={{ label: "Run identification", to: "device-id" }}
        secondaryAction={{ label: "Open report", to: "report" }}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <DashboardStat
          label="Evidence items"
          value={String(evidence.length)}
          icon={HardDrive}
          tone="info"
        />
        <DashboardStat
          label="OEM identified"
          value={coveragePct}
          hint={`${identified} of ${evidence.length} imaged`}
          icon={Shield}
          tone="success"
        />
        <DashboardStat
          label="Recovered segments"
          value={segmentTotal.toLocaleString()}
          icon={ScanSearch}
        />
        <DashboardStat
          label="Failed jobs"
          value={String(flagged).padStart(2, "0")}
          icon={Shield}
          tone={flagged > 0 ? "danger" : "success"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="visily-card">
          <div className="visily-card-header">
            <span className="visily-card-title">Recovery jobs</span>
            <Link
              to="recover"
              className="text-[11px] font-semibold uppercase tracking-wide text-[var(--accent-500)]"
            >
              Manage
            </Link>
          </div>
          <div className="space-y-3 p-4">
            {sortedJobs.slice(0, 5).map((job) => {
              const live = liveJobState[job.id];
              const stats = parseJobStats(job.stats_json);
              const progress = jobDisplayProgress(job, live?.progress);
              const isRunning =
                job.status === "running" || job.status === "pending";
              return (
                <JobProgressCard
                  key={job.id}
                  title={`${job.vendor ?? "Unknown OEM"} // ${job.adapter ?? "pending adapter"}`}
                  subtitle={
                    live?.message ??
                    (stats.segmentsFound != null
                      ? `${stats.segmentsFound} segment${stats.segmentsFound === 1 ? "" : "s"} indexed`
                      : (job.error ?? job.status))
                  }
                  status={
                    job.status === "completed"
                      ? "completed"
                      : isRunning
                        ? "running"
                        : job.status === "failed" || job.status === "error"
                          ? "failed"
                          : "idle"
                  }
                  progress={progress}
                />
              );
            })}
            {jobs.length === 0 ? (
              <JobProgressCard
                title="No recovery jobs"
                subtitle="Acquire evidence on the Acquisition screen, then run recovery."
                status="idle"
              />
            ) : null}
          </div>
        </section>

        <div className="space-y-4">
          <IntegrityPanel
            state={custody}
            lastAudit={
              events.length > 0
                ? events[events.length - 1].created_at
                    .replace("T", " ")
                    .slice(0, 19)
                : "No events yet"
            }
            witnessHash={chainTip ?? undefined}
            onVerify={() =>
              void api.custodyStatus(caseId).then((s) => {
                setCustody(s.intact ? "intact" : "broken");
                setChainTip(s.tip_hash ?? null);
              })
            }
          />
          <AuditLogPanel
            entries={events.slice(-8).map((e) => ({
              id: e.id,
              time: e.created_at.replace("T", " ").replace("Z", " UTC"),
              actor: e.actor,
              action: e.detail ? `${e.action} (${e.detail})` : e.action,
            }))}
          />
        </div>
      </div>

      <section className="visily-card">
        <div className="visily-card-header">
          <span className="visily-card-title">Evidence acquisitions</span>
          <Link
            to="evidence"
            className="text-[11px] font-semibold uppercase tracking-wide text-[var(--accent-500)]"
          >
            Catalog
          </Link>
        </div>
        {evidence.length === 0 ? (
          <p className="p-8 text-[13px] text-[var(--text-secondary)]">
            No evidence yet. Use{" "}
            <Link to="acquire" className="text-[var(--accent-500)] underline">
              Acquisition
            </Link>{" "}
            to image or register a disk.
          </p>
        ) : (
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
            {evidence.slice(0, 4).map((e) => (
              <EvidenceTile
                key={e.id}
                id={e.id}
                caseId={caseId}
                label={e.filename}
                sizeBytes={e.size_bytes}
                sha256={e.sha256}
                status={integrityLabel(
                  resolveIntegrityState(
                    e.acquisition_status,
                    e.verification_status,
                  ),
                )}
                kind={e.media_type?.includes("mobile") ? "mobile" : "disk"}
              />
            ))}
          </div>
        )}
        {evidence.length > 0 ? (
          <div
            className="border-t px-4 py-2"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <p className="mono text-[10px] text-[var(--text-tertiary)]">
              {formatBytes(totalBytes)} total · {evidence.length} item
              {evidence.length === 1 ? "" : "s"}
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
