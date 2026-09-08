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
  jobKindLabel,
  parseJobStats,
  recoveredSegmentsByKind,
  runningJobs,
  summariseSegmentKinds,
  totalRecoveredSegments,
} from "@/lib/caseStats";
import { formatBytes } from "@/lib/utils";
import {
  custodyActionLabel,
  integrityLabel,
  isVendorParserHit,
  recoveryAdapterLabel,
  resolveIntegrityState,
} from "@/lib/integrity";

export function CaseOverviewPage() {
  const { caseId, workspace } = useCaseContext();
  const [custody, setCustody] = useState<ChainLinkState>("checking");
  const [chainTip, setChainTip] = useState<string | null>(null);
  const [brokenRowId, setBrokenRowId] = useState<number | null>(null);
  const [liveJobState, setLiveJobState] = useState<
    Record<string, { progress: number; message: string }>
  >({});

  useEffect(() => {
    void api
      .custodyStatus(caseId)
      .then((s) => {
        setCustody(s.intact ? "intact" : "broken");
        setChainTip(s.tip_hash ?? null);
        setBrokenRowId(s.first_broken_row_id);
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
  // Recordings, carves and filesystem-undelete fragments are different findings.
  // When the engine reported a per-kind split, show the recording count as the
  // headline and the full split beneath it, so a pile of byte-scale FAT
  // fragments never reads as a recording count.
  const segmentKinds = recoveredSegmentsByKind(jobs);
  const flagged = failedJobCount(jobs);
  // A vendor hit means a validated vendor parser matched (Dahua, Hikvision,
  // Honeywell). A generic MBR/FAT/NTFS signature routes to generic_tier2, and a
  // family-signature-only match (CP Plus, Uniview) is a routing hint, not an
  // identification. Neither is counted here.
  const hasVendorHit = (e: (typeof evidence)[number]) =>
    (e.identification?.hits ?? []).some(isVendorParserHit);
  const vendorHit = evidence.filter(hasVendorHit).length;
  const identifyRan = evidence.filter((e) => e.identification != null).length;
  const noValidatedParser = identifyRan - vendorHit;
  const identifyPending = evidence.length - identifyRan;
  const sortedJobs = jobs
    .filter((j) => j.kind === "recovery")
    .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
  const jobActivity = [...jobs]
    .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""))
    .slice(0, 12);

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
          label="Vendor identified"
          value={`${vendorHit} of ${evidence.length}`}
          hint={
            identifyPending > 0
              ? `${noValidatedParser} no validated parser, ${identifyPending} not yet identified`
              : `${noValidatedParser} no validated parser`
          }
          icon={Shield}
          tone={vendorHit > 0 ? "success" : undefined}
        />
        <DashboardStat
          label={segmentKinds ? "Recordings recovered" : "Recovered artifacts"}
          value={(segmentKinds
            ? segmentKinds.recording
            : segmentTotal
          ).toLocaleString()}
          hint={
            segmentKinds
              ? summariseSegmentKinds(segmentKinds)
              : "open Recovery for the recording, carve and filesystem-undelete split"
          }
          icon={ScanSearch}
        />
        <DashboardStat
          label="Failed jobs"
          value={String(flagged)}
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
                  title={`${job.vendor ?? "Vendor not identified"} · ${recoveryAdapterLabel(job.adapter)}`}
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
            {sortedJobs.length === 0 ? (
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
            brokenRowId={brokenRowId}
            onVerify={() =>
              void api.custodyStatus(caseId).then((s) => {
                setCustody(s.intact ? "intact" : "broken");
                setChainTip(s.tip_hash ?? null);
                setBrokenRowId(s.first_broken_row_id);
              })
            }
          />
          <AuditLogPanel
            entries={events.slice(-8).map((e) => ({
              id: e.id,
              time: e.created_at.replace("T", " ").replace("Z", " UTC"),
              actor: e.actor,
              action: e.detail
                ? `${custodyActionLabel(e.action)} (${e.detail})`
                : custodyActionLabel(e.action),
            }))}
          />

          <section className="visily-card">
            <div className="visily-card-header">
              <span className="visily-card-title">Job activity</span>
            </div>
            {jobActivity.length === 0 ? (
              <p className="p-4 text-[13px] text-[var(--text-secondary)]">
                No jobs run yet.
              </p>
            ) : (
              <ul className="divide-y divide-[var(--border-subtle)]">
                {jobActivity.map((job) => (
                  <li
                    key={job.id}
                    className="flex items-center justify-between gap-3 px-4 py-2 text-[12px]"
                  >
                    <span className="font-medium text-[var(--text-primary)]">
                      {jobKindLabel(job.kind)}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="mono text-[11px] text-[var(--text-tertiary)]">
                        {(job.started_at ?? "").replace("T", " ").slice(0, 19)}
                      </span>
                      <span
                        className={
                          job.status === "completed"
                            ? "text-[var(--status-success)]"
                            : job.status === "failed" || job.status === "error"
                              ? "text-[var(--status-danger)]"
                              : "text-[var(--status-info)]"
                        }
                      >
                        {job.status}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
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
