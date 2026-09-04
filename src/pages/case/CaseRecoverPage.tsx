import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type Segment } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge } from "@/components/forensic/ConfidenceBadge";
import { RecoveryLogPanel } from "@/components/forensic/RecoveryLogPanel";
import { RecoveryLastRun } from "@/components/forensic/RecoveryLastRun";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { RecoveryChecksPanel } from "@/components/forensic/RecoveryChecksPanel";
import { RecoveryDiskMap } from "@/components/forensic/RecoveryDiskMap";
import { RecoveryTelemetryRibbon } from "@/components/forensic/RecoveryTelemetryRibbon";
import { SegmentInspector } from "@/components/forensic/SegmentInspector";
import { VirtualTable } from "@/components/ui/virtual-table";
import { subscribeJobEvents } from "@/lib/sse";
import { useActivity } from "@/context/ActivityContext";
import { cn, formatBytes } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";
import {
  allocationDetail,
  allocationLabel,
  allocationOf,
  countAllocations,
  summariseAllocations,
  type AllocationState,
} from "@/lib/allocation";
import { timestampTier } from "@/lib/checks";
import "@/styles/recovery.css";

/**
 * Allocation state cell. Colour is a reinforcement, never the only signal:
 * every state carries a distinct glyph and a written label, so the column
 * survives greyscale printing and colour-vision deficiency.
 */
function AllocationCell({ state }: { state: AllocationState }) {
  const style: Record<AllocationState, { glyph: string; color: string }> = {
    deleted: { glyph: "✕", color: "var(--status-danger)" },
    recording: { glyph: "●", color: "var(--status-info)" },
    allocated: { glyph: "✓", color: "var(--status-success)" },
    unknown: { glyph: "?", color: "var(--text-tertiary)" },
  };
  const { glyph, color } = style[state];
  return (
    <span
      className="rec-pill text-[10.5px] font-semibold uppercase tracking-wide"
      style={{ color }}
    >
      <span aria-hidden="true">{glyph}</span>
      {allocationLabel(state)}
    </span>
  );
}

/**
 * Determinate recovery progress.
 *
 * The engine emits `progress` on every job event (recovery.py: 1 -> 10 -> 12 ->
 * per-segment -> 100). The page previously discarded it and showed only a
 * scrolling log, which on a multi-terabyte image told the examiner nothing about
 * how far along the run was. Falls back to an indeterminate bar only while the
 * first event is still in flight.
 */
function RecoveryProgress({
  percent,
  phase,
}: {
  percent: number | null;
  phase: string | null;
}) {
  const known = typeof percent === "number" && Number.isFinite(percent);
  const clamped = known ? Math.max(0, Math.min(100, percent)) : 0;
  return (
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="truncate text-[12px] text-[var(--text-secondary)]">
          {phase ?? "Waiting for the engine…"}
        </span>
        <span className="mono shrink-0 text-[12px] font-medium text-[var(--text-primary)]">
          {known ? `${clamped.toFixed(0)}%` : "—"}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? Math.round(clamped) : undefined}
        aria-label="Recovery progress"
        className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-4)]"
      >
        <div
          className={cn(
            "h-full rounded-full bg-[var(--accent-500)] transition-[width] duration-300 ease-out",
            known ? "" : "w-1/3 animate-pulse",
          )}
          style={known ? { width: `${clamped}%` } : undefined}
        />
      </div>
    </div>
  );
}

/**
 * Statuses that mean a recovery stopped part-way through writing its results.
 *
 * `run_recovery_job` supersedes the device's prior segments *before* it writes
 * the new ones, so an aborted run can leave the table showing fewer recordings
 * than the image contains — measured: a run cancelled early leaves 0 segments
 * where a full run yields 5. Nothing in the stored data marks that set partial,
 * which is why this has to be surfaced at the UI.
 */
const ABORTED_JOB_STATUSES = new Set(["cancelled", "interrupted"]);

/**
 * Poll a job's real terminal status after a cancel request.
 *
 * `POST /jobs/{id}/cancel` flags the job and returns `cancelled`, but the
 * running scan is not actually aborted — it continues and rewrites the status
 * to `completed` on its own. Measured on the emulated image: `cancelled` with 0
 * segments at t=0, `completed` with all 5 at t=250 ms. Until the engine
 * genuinely aborts, the UI must not report an outcome until the status settles.
 */
async function confirmCancellation(
  jobId: string,
  attempts = 12,
  intervalMs = 400,
): Promise<{ status: string }> {
  let last = "cancelled";
  for (let i = 0; i < attempts; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    try {
      const detail = await api.getJob(jobId);
      last = detail.job.status;
      // The scan ran to completion despite the cancel — stop early and say so.
      if (last === "completed" || last === "failed") return { status: last };
    } catch {
      break;
    }
  }
  return { status: last };
}

/**
 * Persistent warning that the visible dataset is not a complete recovery.
 *
 * Deliberately rendered inside the segments card, directly above the table
 * header, so the table cannot be screenshotted without it.
 */
function PartialResultBanner({
  status,
  segmentCount,
}: {
  status: string;
  segmentCount: number;
}) {
  const aborted = status === "cancelled" ? "cancelled" : "interrupted";
  return (
    <div
      role="alert"
      className="flex shrink-0 items-start gap-2.5 border-b border-[var(--status-warning)] bg-[rgba(217,119,6,0.12)] px-4 py-3"
    >
      <span
        aria-hidden="true"
        className="mt-px shrink-0 text-[14px] leading-none text-[var(--status-warning)]"
      >
        ⚠
      </span>
      <div className="min-w-0 text-[12px] leading-relaxed">
        <p className="font-semibold text-[var(--status-warning)]">
          Incomplete recovery — this is not a full result set
        </p>
        <p className="mt-0.5 text-[var(--text-secondary)]">
          The last recovery run for this evidence image was{" "}
          <strong>{aborted} mid-scan</strong>, so the engine stopped before it
          finished enumerating the image.{" "}
          <strong>
            The {segmentCount} {segmentCount === 1 ? "recording" : "recordings"}{" "}
            shown below
            {segmentCount === 0 ? " (none)" : ""} do not represent everything
            present on this evidence.
          </strong>{" "}
          Re-run recovery to completion before drawing any forensic conclusion,
          citing these results in a report, or exporting them as evidence.
        </p>
      </div>
    </div>
  );
}

export function CaseRecoverPage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [deviceId, setDeviceId] = useState("");
  const [actor, setActor] = useState(workspace?.case.examiner_name ?? "");
  const [log, setLog] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  // The recovery job this page is currently streaming. The SSE subscription is
  // owned by an effect keyed on this, never by an async handler, so it is always
  // torn down on unmount — see the effect below.
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [starting, setStarting] = useState(false);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(
    null,
  );
  const [adapters, setAdapters] = useState<string[]>([]);
  // null = follow Identification. A string is a deliberate examiner override.
  const [manualAdapter, setManualAdapter] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [deletedOnly, setDeletedOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<string | null>("range");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const { setWorking, setIdle } = useActivity();

  useEffect(() => {
    void api
      .version()
      .then((v) => setAdapters(v.capabilities.recovery_adapters ?? []));
  }, []);

  const selectedEvidence = useMemo(
    () => workspace?.evidence.find((e) => e.id === deviceId) ?? null,
    [workspace?.evidence, deviceId],
  );

  const recommendedAdapter =
    selectedEvidence?.identification?.recommended_adapter;

  const hasRecommendation = Boolean(
    recommendedAdapter && recommendedAdapter !== "needs_selection",
  );

  // The adapter actually sent to the engine. Identification decides unless the
  // examiner has explicitly overridden it for this device.
  const effectiveAdapter = useMemo(() => {
    if (manualAdapter) return manualAdapter;
    if (hasRecommendation) return recommendedAdapter as string;
    return "";
  }, [manualAdapter, hasRecommendation, recommendedAdapter]);

  // Switching evidence must drop the previous device's override, otherwise the
  // next image silently runs under the wrong parser.
  useEffect(() => {
    setManualAdapter(null);
  }, [deviceId]);

  // Identification could not decide: the examiner has to, so surface the control.
  useEffect(() => {
    if (!deviceId) return;
    setAdvancedOpen(!hasRecommendation);
  }, [deviceId, hasRecommendation]);

  useEffect(() => {
    if (workspace?.evidence[0] && !deviceId)
      setDeviceId(workspace.evidence[0].id);
  }, [workspace, deviceId]);

  useEffect(() => {
    if (!deviceId) {
      setSegments([]);
      return;
    }
    void api
      .listDeviceSegments(deviceId)
      .then((r) => setSegments(r.segments))
      .catch(() => setSegments([]));
  }, [deviceId, workspace?.jobs]);

  // Allocation is derived once per segments change, not per render and never
  // inside the virtualizer's row renderer — that would run on every scroll frame.
  const allocationCounts = useMemo(
    () => countAllocations(segments),
    [segments],
  );

  const allocationByRow = useMemo(() => {
    const map = new Map<string, AllocationState>();
    for (const segment of segments) map.set(segment.id, allocationOf(segment));
    return map;
  }, [segments]);

  /**
   * Free-text match across the fields an examiner actually searches by:
   * channel, byte offsets (decimal or hex), state, validation, parser and the
   * recorder timestamp. Matching is done on a prebuilt lowercase haystack so a
   * keystroke costs one pass, not a re-derivation per row per render.
   */
  const haystacks = useMemo(() => {
    const map = new Map<string, string>();
    for (const seg of segments) {
      const start = seg.offset_start ?? 0;
      const end = seg.offset_end ?? 0;
      map.set(
        seg.id,
        [
          `ch${seg.channel ?? ""}`,
          String(start),
          String(end),
          `0x${start.toString(16)}`,
          `0x${end.toString(16)}`,
          allocationByRow.get(seg.id) ?? "",
          seg.validation ?? "",
          seg.parser_name ?? "",
          seg.recorder_start_ts ?? "",
          seg.timestamp_source ?? "",
        ]
          .join(" ")
          .toLowerCase(),
      );
    }
    return map;
  }, [segments, allocationByRow]);

  const visibleSegments = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let rows = deletedOnly
      ? segments.filter((s) => allocationByRow.get(s.id) === "deleted")
      : segments;
    if (needle) {
      rows = rows.filter((s) => haystacks.get(s.id)?.includes(needle));
    }
    if (!sortKey) return rows;

    const value = (seg: Segment): string | number => {
      switch (sortKey) {
        case "ch":
          return seg.channel ?? -1;
        case "state":
          return allocationByRow.get(seg.id) ?? "";
        case "range":
          return seg.offset_start ?? 0;
        case "size":
          return (
            seg.byte_length ?? (seg.offset_end ?? 0) - (seg.offset_start ?? 0)
          );
        case "ts":
          return seg.recorder_start_ts ?? "";
        case "validation":
          return seg.timestamp_confidence ?? -1;
        default:
          return 0;
      }
    };
    // Copy before sorting: never mutate the array the rest of the page reads.
    return [...rows].sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [
    segments,
    deletedOnly,
    allocationByRow,
    haystacks,
    query,
    sortKey,
    sortDir,
  ]);

  function handleSort(key: string) {
    if (key === sortKey) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  // Never leave the inspector pinned to a row the filter has hidden.
  useEffect(() => {
    if (!selectedSegmentId) return;
    if (!visibleSegments.some((s) => s.id === selectedSegmentId)) {
      setSelectedSegmentId(null);
    }
  }, [visibleSegments, selectedSegmentId]);

  const recoveryRunning = useMemo(
    () =>
      workspace?.jobs.some(
        (job) =>
          job.kind === "recovery" &&
          (job.device_id === deviceId || job.image_id === deviceId) &&
          (job.status === "running" || job.status === "pending"),
      ) ?? false,
    [workspace?.jobs, deviceId],
  );

  /**
   * Terminal status of the most recent recovery run for this device.
   *
   * workspace.jobs arrives ordered created_at DESC (repository.list_jobs_for_case),
   * so the first terminal entry is the latest finished run. A later successful
   * run therefore clears the warning on its own.
   */
  const lastFinishedRecovery = useMemo(() => {
    if (!deviceId) return null;
    return (
      workspace?.jobs.find(
        (job) =>
          job.kind === "recovery" &&
          (job.device_id === deviceId || job.image_id === deviceId) &&
          job.status !== "running" &&
          job.status !== "pending",
      ) ?? null
    );
  }, [workspace?.jobs, deviceId]);

  const partialResultStatus =
    lastFinishedRecovery &&
    ABORTED_JOB_STATUSES.has(lastFinishedRecovery.status)
      ? lastFinishedRecovery.status
      : null;

  // True while this page is streaming a job, or the workspace still reports one
  // running for this device (covers the gap before the first SSE event lands).
  const isRecovering = activeJobId !== null || recoveryRunning;

  useEffect(() => {
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [log]);

  // Keep the effect below free of changing dependencies: re-running it would
  // tear down and re-open a live SSE connection mid-recovery.
  const finishRef = useRef({ refresh, setWorking, setIdle });
  finishRef.current = { refresh, setWorking, setIdle };

  /**
   * Owns the job event stream for the lifetime of `activeJobId`.
   *
   * The subscription used to live inside the click handler, whose unsubscribe
   * function was discarded — navigating away mid-recovery leaked the
   * EventSource and kept setState running on an unmounted component. Here the
   * cleanup is returned to React, so unmount, device change and job completion
   * all close the connection exactly once.
   */
  useEffect(() => {
    if (!activeJobId) return;
    let cancelledByUnmount = false;
    finishRef.current.setWorking("Recovery running…");

    const settle = () => {
      if (cancelledByUnmount) return;
      setActiveJobId(null);
      setCancelling(false);
      setProgress(null);
      setPhase(null);
      finishRef.current.setIdle();
    };

    const unsubscribe = subscribeJobEvents(activeJobId, {
      onEvent: (event) => {
        if (cancelledByUnmount) return;
        if (typeof event.progress === "number") setProgress(event.progress);
        if (event.message) {
          setPhase(event.message);
          setLog((prev) => [...prev.slice(-200), event.message!]);
        }
        if (event.status === "completed") {
          void api
            .getJob(activeJobId)
            .then(async (result) => {
              if (cancelledByUnmount) return;
              setSegments(result.segments);
              toast.success(`${result.segments.length} sequences recovered`);
              await finishRef.current.refresh();
            })
            .catch(() => undefined)
            .finally(settle);
          return;
        }
        if (event.status === "cancelled") {
          // The engine does not currently abort on cancel: it flags the job,
          // keeps scanning, and overwrites the status with `completed` when it
          // finishes (measured: cancelled at t=0 with 0 segments, completed at
          // t=250ms with all 5). Reporting "cancelled" here would tell the
          // examiner a scan had stopped while it was still running and writing.
          // So confirm the job's real terminal state before saying anything.
          setPhase("Cancel requested — confirming the engine stopped…");
          void confirmCancellation(activeJobId)
            .then(async (outcome) => {
              if (cancelledByUnmount) return;
              if (outcome.status === "completed") {
                const result = await api.getJob(activeJobId);
                setSegments(result.segments);
                toast.warning(
                  `Too late to cancel — the run finished with ${result.segments.length} sequences`,
                  { duration: 10_000 },
                );
              } else {
                toast.message("Recovery cancelled");
              }
              await finishRef.current.refresh();
            })
            .catch(() => undefined)
            .finally(settle);
          return;
        }
        if (event.status === "failed" || event.status === "interrupted") {
          toast.error(
            event.error || event.message || `Recovery ${event.status}`,
            { duration: Infinity },
          );
          settle();
        }
      },
      onError: (err) => {
        if (cancelledByUnmount) return;
        toast.error(err.message || "Lost connection to the recovery job", {
          duration: Infinity,
        });
        settle();
      },
    });

    return () => {
      // Unmount / job change: close the stream and stop touching state.
      cancelledByUnmount = true;
      unsubscribe();
      finishRef.current.setIdle();
    };
  }, [activeJobId]);

  // Reattach to a recovery already running for this device (page reload, or the
  // examiner navigating back mid-run) so progress and cancel stay available.
  useEffect(() => {
    if (activeJobId || !deviceId) return;
    const running = workspace?.jobs.find(
      (job) =>
        job.kind === "recovery" &&
        (job.device_id === deviceId || job.image_id === deviceId) &&
        (job.status === "running" || job.status === "pending"),
    );
    if (running) setActiveJobId(running.id);
  }, [workspace?.jobs, deviceId, activeJobId]);

  async function handleRecover() {
    if (!deviceId || !actor.trim()) {
      toast.error("Select device and enter examiner");
      return;
    }
    if (!effectiveAdapter) {
      toast.error(
        "Identification could not determine a parser — pick one under Advanced",
      );
      setAdvancedOpen(true);
      return;
    }
    setStarting(true);
    setLog([]);
    setProgress(0);
    setPhase("Starting recovery…");
    try {
      const started = await api.recover(
        caseId,
        deviceId,
        actor.trim(),
        effectiveAdapter,
      );
      setActiveJobId(started.job.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Recovery failed", {
        duration: Infinity,
      });
      setProgress(null);
      setPhase(null);
    } finally {
      setStarting(false);
    }
  }

  async function handleCancel() {
    if (!activeJobId) return;
    setCancelling(true);
    try {
      await api.cancelJob(activeJobId);
      // The terminal `cancelled` event settles the UI; if the job finished in
      // the race, the completion event settles it instead.
    } catch (err) {
      setCancelling(false);
      toast.error(
        err instanceof Error ? err.message : "Could not cancel the job",
      );
    }
  }

  const selectedSegment = useMemo(
    () => segments.find((s) => s.id === selectedSegmentId) ?? null,
    [segments, selectedSegmentId],
  );

  return (
    // On a short viewport the page scrolls rather than compressing panels to
    // zero height — a collapsed segments table is worse than a scrollbar.
    <TooltipProvider delayDuration={250} skipDelayDuration={300}>
      <div className="recovery-shell flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
        {/* shrink-0 + overflow-visible: .visily-card clips, and as a flex child this
          card was compressing, so the expanded Advanced panel was cut in half. */}
        <section className="visily-card flex shrink-0 flex-wrap items-end gap-3 overflow-visible p-4">
          <div className="min-w-[180px] flex-1">
            <label className="label">Evidence image</label>
            <select
              className="field w-full"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            >
              {(workspace?.evidence ?? []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.filename}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[160px]">
            <label className="label">Examiner</label>
            <Input value={actor} onChange={(e) => setActor(e.target.value)} />
          </div>
          <div className="min-w-[220px]">
            <label className="label">Recovery parser</label>
            <div className="flex h-[34px] items-center gap-2">
              {effectiveAdapter ? (
                <span className="mono text-[13px] font-medium text-[var(--text-primary)]">
                  {effectiveAdapter}
                </span>
              ) : (
                <span className="text-[13px] text-[var(--status-warning)]">
                  Not determined
                </span>
              )}
              {manualAdapter ? (
                <Badge variant="warning">manual override</Badge>
              ) : hasRecommendation ? (
                <Badge variant="info">auto</Badge>
              ) : null}
            </div>
          </div>
          <Button
            disabled={starting || !deviceId || isRecovering}
            onClick={() => void handleRecover()}
          >
            {starting
              ? "Starting…"
              : isRecovering
                ? "Recovery in progress…"
                : "Run recovery"}
          </Button>

          <div className="w-full">
            <button
              type="button"
              onClick={() => setAdvancedOpen((open) => !open)}
              aria-expanded={advancedOpen}
              className="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            >
              {advancedOpen ? "▾" : "▸"} Advanced
            </button>

            {advancedOpen ? (
              <div className="rec-well mt-2 flex flex-wrap items-end gap-3 rounded border border-[var(--border-subtle)] p-3">
                <div className="min-w-[200px]">
                  <label className="label">Override parser</label>
                  <select
                    className="field w-full"
                    value={effectiveAdapter}
                    onChange={(e) => setManualAdapter(e.target.value)}
                  >
                    {!effectiveAdapter ? (
                      <option value="">Select a parser…</option>
                    ) : null}
                    {adapters.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                {manualAdapter && hasRecommendation ? (
                  <Button
                    variant="ghost"
                    onClick={() => setManualAdapter(null)}
                    title={`Revert to ${recommendedAdapter}`}
                  >
                    Reset to auto
                  </Button>
                ) : null}
                <p className="w-full text-[12px] text-[var(--text-secondary)]">
                  {manualAdapter && hasRecommendation ? (
                    <span className="text-[var(--status-warning)]">
                      Overriding Identification, which recommends{" "}
                      <span className="mono font-medium">
                        {recommendedAdapter}
                      </span>
                      . Recorded in the recovery job.
                    </span>
                  ) : hasRecommendation ? (
                    <>
                      Identification recommends{" "}
                      <span className="mono font-medium">
                        {recommendedAdapter}
                      </span>
                      . Override only if you have reason to.
                    </>
                  ) : (
                    <span className="text-[var(--status-warning)]">
                      Identification could not determine a parser for this image
                      — select one manually.
                    </span>
                  )}
                </p>
              </div>
            ) : null}
          </div>

          <div className="-mx-4 -mb-4 mt-1 w-[calc(100%+2rem)]">
            <RecoveryTelemetryRibbon
              segments={segments}
              evidence={selectedEvidence}
              adapter={effectiveAdapter}
            />
          </div>
        </section>

        {/* Two-column workspace: the evidence the examiner works on is on the
          left and gets the width; the run's context sits beside it instead of
          pushing the table below the fold. Stacks under 1280px. */}
        <div className="grid min-h-0 shrink-0 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col gap-3">
            <section className="visily-card shrink-0 overflow-hidden">
              <div className="visily-card-header">
                <span className="visily-card-title">Disk map</span>
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  Byte offsets across the evidence image
                </span>
              </div>
              <RecoveryDiskMap
                segments={segments}
                scanning={isRecovering}
                imageSize={selectedEvidence?.size_bytes ?? 0}
                selectedSegmentId={selectedSegmentId}
                onSelect={(id) => {
                  setDeletedOnly(false);
                  setSelectedSegmentId(id);
                }}
              />
            </section>
            <section className="visily-card shrink-0 overflow-hidden">
              {partialResultStatus && !isRecovering ? (
                <PartialResultBanner
                  status={partialResultStatus}
                  segmentCount={segments.length}
                />
              ) : null}
              <div className="visily-card-header">
                <span className="visily-card-title">Recovered segments</span>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <span className="text-[11px] text-[var(--text-secondary)]">
                    {visibleSegments.length !== segments.length
                      ? `${visibleSegments.length} of ${segments.length} shown`
                      : summariseAllocations(segments.length, allocationCounts)}
                  </span>
                  <input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Filter offset, channel, state…"
                    aria-label="Filter recovered segments"
                    className="field mono h-6 w-52 text-[11px]"
                  />
                  <button
                    type="button"
                    role="switch"
                    aria-checked={deletedOnly}
                    disabled={allocationCounts.deleted === 0}
                    onClick={() => setDeletedOnly((on) => !on)}
                    className={cn(
                      "rounded border px-2 py-0.5 text-[11px] transition-colors",
                      deletedOnly
                        ? "border-[var(--status-danger)] bg-[rgba(220,38,38,0.12)] text-[var(--status-danger)]"
                        : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--surface-3)]",
                      allocationCounts.deleted === 0
                        ? "cursor-not-allowed opacity-40"
                        : "",
                    )}
                    title={
                      allocationCounts.deleted === 0
                        ? "No deleted recordings on this image"
                        : "Show only recordings recovered from cleared index entries"
                    }
                  >
                    Deleted only
                  </button>
                </div>
              </div>
              <VirtualTable
                rows={visibleSegments}
                rowHeight={48}
                maxHeight={288}
                minWidth={880}
                emptyMessage={
                  query.trim()
                    ? `No recovered segment matches "${query.trim()}".`
                    : deletedOnly
                      ? "No deleted recordings on this image."
                      : "No segments for this device yet."
                }
                getRowKey={(seg) => seg.id}
                sortKey={sortKey}
                sortDir={sortDir}
                onSortChange={handleSort}
                selectedRowKey={selectedSegmentId}
                onRowClick={(seg) => setSelectedSegmentId(seg.id)}
                getRowTitle={(seg) => allocationDetail(seg)}
                // Inset shadow, not a border: a border would consume 4px of layout and
                // shift every marked row out of alignment with the header.
                getRowClassName={(seg) =>
                  (seg.id === selectedSegmentId ? "rec-row-selected " : "") +
                  (allocationByRow.get(seg.id) === "deleted"
                    ? "rec-row rec-row-deleted shadow-[inset_4px_0_0_0_var(--status-danger)] bg-[rgba(220,38,38,0.06)]"
                    : allocationByRow.get(seg.id) === "recording"
                      ? "rec-row shadow-[inset_4px_0_0_0_var(--status-info)]"
                      : "rec-row")
                }
                columns={[
                  {
                    key: "ch",
                    sortable: true,
                    header: "Ch",
                    width: "56px",
                    cell: (seg) => seg.channel ?? "—",
                  },
                  {
                    key: "state",
                    sortable: true,
                    header: "State",
                    width: "124px",
                    cell: (seg) => {
                      const state = allocationByRow.get(seg.id) ?? "unknown";
                      return <AllocationCell state={state} />;
                    },
                  },
                  {
                    key: "range",
                    sortable: true,
                    header: "Byte range",
                    width: "minmax(132px, 1.2fr)",
                    className: "mono",
                    cell: (seg) =>
                      seg.offset_start != null && seg.offset_end != null ? (
                        <span className="rec-offset">
                          {seg.offset_start}–{seg.offset_end}
                        </span>
                      ) : (
                        (seg.offset_time_label ?? "—")
                      ),
                  },
                  {
                    key: "size",
                    sortable: true,
                    header: "Size",
                    width: "84px",
                    className: "mono",
                    cell: (seg) =>
                      formatBytes(
                        seg.byte_length ??
                          (seg.offset_end ?? 0) - (seg.offset_start ?? 0),
                      ),
                  },
                  {
                    key: "frames",
                    header: "Playable frames",
                    width: "84px",
                    className: "mono",
                    cell: (seg) => (
                      <span
                        title={
                          seg.playable_frame_count != null
                            ? undefined
                            : "Measured by ffprobe when the recording is exported"
                        }
                      >
                        {seg.playable_frame_count != null
                          ? String(seg.playable_frame_count)
                          : "—"}
                      </span>
                    ),
                  },
                  {
                    key: "ts",
                    sortable: true,
                    header: "Timestamp",
                    width: "minmax(150px, 1.4fr)",
                    cell: (seg) => (
                      <div className="text-[11px]">
                        <div>
                          {seg.corrected_start_ts ??
                            seg.recorder_start_ts ??
                            "—"}
                        </div>
                        <div className="text-[var(--text-tertiary)]">
                          {formatTimestampSource(seg.timestamp_source)}
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: "parser",
                    header: "Parser",
                    width: "92px",
                    className: "mono text-[10px]",
                    cell: (seg) => seg.parser_name ?? "—",
                  },
                  {
                    key: "validation",
                    sortable: true,
                    header: "Validation",
                    width: "minmax(158px, 1.3fr)",
                    cell: (seg) => (
                      <div className="flex flex-col gap-0.5">
                        <ConfidenceBadge
                          tier={timestampTier(seg.timestamp_confidence)}
                          label={seg.validation?.replace(/_/g, " ")}
                        />
                        <Tooltip
                          content={
                            (seg.validation_evidence?.[
                              "timestamp_confidence_basis"
                            ] as string) || undefined
                          }
                        >
                          <span className="mono w-fit cursor-help border-b border-dotted border-[var(--border-strong)] text-[10px] text-[var(--text-tertiary)]">
                            {seg.timestamp_confidence != null
                              ? `ts conf ${seg.timestamp_confidence}`
                              : "ts conf —"}
                          </span>
                        </Tooltip>
                      </div>
                    ),
                  },
                ]}
              />
            </section>
          </div>

          <div className="flex min-w-0 flex-col gap-3">
            <section className="visily-card overflow-auto p-4">
              <p className="visily-card-title mb-3">Checks passed</p>
              <RecoveryChecksPanel segments={segments} />
            </section>
            <section className="visily-card flex min-h-[240px] flex-col overflow-hidden">
              <div className="visily-card-header">
                <span className="visily-card-title">Engine log</span>
                {isRecovering ? (
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={cancelling || !activeJobId}
                    title="Asks the engine to stop. A scan already near completion may still finish — the result is confirmed before anything is reported."
                    onClick={() => void handleCancel()}
                  >
                    {cancelling ? "Requesting stop…" : "Request cancel"}
                  </Button>
                ) : null}
              </div>
              {isRecovering ? (
                <RecoveryProgress percent={progress} phase={phase} />
              ) : null}
              <div
                ref={logRef}
                className="flex min-h-[240px] flex-1 flex-col overflow-hidden"
              >
                {log.length > 0 || isRecovering ? (
                  <RecoveryLogPanel lines={log} />
                ) : (
                  <RecoveryLastRun
                    job={lastFinishedRecovery}
                    segments={segments}
                  />
                )}
              </div>
            </section>
          </div>
        </div>

        <SegmentInspector
          caseId={caseId}
          deviceId={deviceId}
          segment={selectedSegment}
          variant="recover"
        />
      </div>
    </TooltipProvider>
  );
}
