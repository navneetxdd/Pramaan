import { useMemo } from "react";
import type { RecoveryJob, Segment } from "@/lib/api";
import { countAllocations } from "@/lib/allocation";

/**
 * What fills the engine log panel between runs.
 *
 * The log is empty except while a job streams, which left roughly a third of
 * the page as a blank rectangle saying "Log output appears when a recovery job
 * runs." This puts the last run's real telemetry there instead: when it ran,
 * which parser, how long it took, and what it found.
 *
 * Everything is read from the persisted job row and the current segment list.
 * Duration is computed from started_at/completed_at and is omitted when either
 * is missing rather than being estimated.
 */

function formatDuration(startIso?: string | null, endIso?: string | null) {
  if (!startIso || !endIso) return null;
  const ms = Date.parse(endIso) - Date.parse(startIso);
  if (!Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

function formatWhen(iso?: string | null) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUS_TONE: Record<string, string> = {
  completed: "var(--status-success)",
  failed: "var(--status-danger)",
  cancelled: "var(--status-warning)",
  interrupted: "var(--status-warning)",
};

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rec-metric">
      <span
        className="rec-metric-value"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </span>
      <span className="rec-metric-label">{label}</span>
    </div>
  );
}

export function RecoveryLastRun({
  job,
  segments,
}: {
  job: RecoveryJob | null;
  segments: Segment[];
}) {
  const counts = useMemo(() => countAllocations(segments), [segments]);
  const channels = useMemo(
    () => new Set(segments.map((s) => s.channel ?? 0)).size,
    [segments],
  );

  if (!job) {
    return (
      <div className="rec-idle flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <span className="rec-idle-glyph" aria-hidden="true" />
        <p className="text-[13px] font-medium text-[var(--text-secondary)]">
          No recovery has been run on this image yet
        </p>
        <p className="max-w-sm text-[11.5px] leading-relaxed text-[var(--text-tertiary)]">
          Run recovery to enumerate the recorder&apos;s index and carve every
          recording it still references — including entries the recorder
          deleted.
        </p>
      </div>
    );
  }

  const duration = formatDuration(job.started_at, job.completed_at);
  const when = formatWhen(job.completed_at ?? job.started_at);
  const tone = STATUS_TONE[job.status] ?? "var(--text-tertiary)";

  return (
    <div className="rec-idle flex flex-1 flex-col justify-center gap-4 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          Last run
        </p>
        <p className="mono text-[11px] text-[var(--text-tertiary)]">
          {when ?? "—"}
        </p>
      </div>

      <div className="rec-metric-row">
        <Metric
          label="Recordings"
          value={String(segments.length)}
          accent="var(--accent-600)"
        />
        <Metric
          label="Deleted"
          value={String(counts.deleted)}
          accent={counts.deleted > 0 ? "var(--status-danger)" : undefined}
        />
        <Metric label="Channels" value={channels ? String(channels) : "—"} />
        <Metric label="Duration" value={duration ?? "—"} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: tone }}
          />
          <span className="font-medium" style={{ color: tone }}>
            {job.status}
          </span>
        </span>
        <span className="text-[var(--text-tertiary)]">
          parser{" "}
          <span className="mono text-[var(--text-secondary)]">
            {job.adapter ?? "—"}
          </span>
        </span>
        {job.error ? (
          <span className="mono text-[var(--status-danger)]">{job.error}</span>
        ) : null}
      </div>

      <p className="text-[11px] text-[var(--text-tertiary)]">
        Engine output streams here live during the next run.
      </p>
    </div>
  );
}
