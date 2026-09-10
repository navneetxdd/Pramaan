import type { TimelineChannel } from "@/lib/api";
import { formatBytes, formatOffset, cn } from "@/lib/utils";

type TimelineViewProps = {
  channels: TimelineChannel[];
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
  onSelectFinding?: (segmentId: string, findingId: string) => void;
  /** From the engine timeline normalization block. Drives the always-visible
   * time-basis line so the examiner can never read the bars without knowing
   * whether the horizontal axis is a recorder clock or just byte order. */
  rtcParsed?: boolean;
  driftSeconds?: number;
};

function timeBasisText(
  useTime: boolean,
  rtcParsed: boolean | undefined,
  driftSeconds: number | undefined,
): string {
  if (!useTime || rtcParsed === false) {
    return "Byte-offset order per channel. No recorder clock was recovered, so bar positions are storage order, not wall-clock time.";
  }
  const drift =
    driftSeconds && Math.abs(driftSeconds) >= 0.5
      ? `calibrated drift ${driftSeconds > 0 ? "+" : ""}${driftSeconds.toFixed(1)}s applied`
      : "no drift correction applied";
  return `Recorder clock, ${drift}. Byte order is retained per channel.`;
}

function segmentSize(seg: TimelineChannel["segments"][0]) {
  return seg.byte_length ?? Math.max(seg.offset_end - seg.offset_start, 1);
}

function parseStart(
  seg: TimelineChannel["segments"][0],
  useTime: boolean,
): number {
  if (useTime) {
    const raw =
      seg.corrected_start_ts ?? seg.recorder_start_ts ?? seg.offset_time_label;
    if (raw) {
      if (/^\d+(\.\d+)?$/.test(raw)) return Number(raw) * 1000;
      const parsed = Date.parse(raw);
      if (!Number.isNaN(parsed)) return parsed;
    }
  }
  return seg.offset_start ?? seg.offset_order ?? 0;
}

function parseEnd(
  seg: TimelineChannel["segments"][0],
  start: number,
  useTime: boolean,
): number {
  if (useTime) {
    const raw = seg.corrected_end_ts ?? seg.recorder_end_ts;
    if (raw) {
      if (/^\d+(\.\d+)?$/.test(raw)) return Number(raw) * 1000;
      const parsed = Date.parse(raw);
      if (!Number.isNaN(parsed)) return parsed;
    }
    return start + 5000;
  }
  return start + segmentSize(seg);
}

function segmentDeleted(seg: TimelineChannel["segments"][0]): boolean {
  if (seg.deleted_candidate) return true;
  return [
    "honeywell_expired_index",
    "filesystem_deleted_inode",
    "unreferenced_carve",
    "h264_nal_tail",
    "slack_recovered",
  ].includes(seg.validation ?? "");
}

function formatRulerLabel(value: number, useTime: boolean): string {
  if (!useTime) return formatOffset(Math.round(value));
  return new Date(value).toISOString().replace("T", " ").slice(11, 19);
}

function buildTicks(min: number, max: number, useTime: boolean): number[] {
  const span = Math.max(max - min, 1);
  const count = 5;
  return Array.from(
    { length: count + 1 },
    (_, index) => min + (span * index) / count,
  );
}

export function TimelineView({
  channels,
  selectedSegmentId,
  onSelect,
  onSelectFinding,
  rtcParsed,
  driftSeconds,
}: TimelineViewProps) {
  if (channels.length === 0) {
    return (
      <p className="text-[13px] text-[var(--text-tertiary)]">
        No segments recovered.
      </p>
    );
  }

  const useTime = channels.some((channel) =>
    channel.segments.some(
      (seg) =>
        !!(
          seg.corrected_start_ts ??
          seg.recorder_start_ts ??
          seg.offset_time_label
        ),
    ),
  );

  let globalMin = Number.POSITIVE_INFINITY;
  let globalMax = Number.NEGATIVE_INFINITY;

  for (const channel of channels) {
    for (const seg of channel.segments) {
      const start = parseStart(seg, useTime);
      const end = parseEnd(seg, start, useTime);
      if (start < globalMin) globalMin = start;
      if (end > globalMax) globalMax = end;
    }
  }

  if (globalMin === Number.POSITIVE_INFINITY) {
    globalMin = 0;
    globalMax = 1;
  }
  const globalSpan = Math.max(globalMax - globalMin, 1);
  const globalTicks = buildTicks(globalMin, globalMax, useTime);

  const axisIsTime = useTime && rtcParsed !== false;

  return (
    <div className="space-y-3">
      <p
        className={
          axisIsTime
            ? "rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2 text-[11px] text-[var(--text-secondary)]"
            : "rounded border border-[var(--status-warning)] bg-[rgba(217,119,6,0.1)] px-3 py-2 text-[11px] text-[var(--text-secondary)]"
        }
      >
        <span className="font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
          Time basis
        </span>{" "}
        {timeBasisText(useTime, rtcParsed, driftSeconds)}
      </p>

      {channels.map((channel) => {
        const sorted = [...channel.segments].sort(
          (a, b) => parseStart(a, useTime) - parseStart(b, useTime),
        );
        const starts = sorted.map((seg) => parseStart(seg, useTime));
        const ends = sorted.map((seg, index) =>
          parseEnd(seg, starts[index], useTime),
        );
        const min = globalMin;
        const max = globalMax;
        const span = globalSpan;
        const ticks = globalTicks;

        return (
          <section
            key={channel.channel}
            className="visily-card overflow-hidden"
          >
            <div className="panel-header">
              <span className="panel-title">{channel.label}</span>
              <span className="mono">
                {channel.segment_count} segments ·{" "}
                {formatBytes(
                  sorted.reduce((sum, seg) => sum + segmentSize(seg), 0),
                )}
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div className="relative h-6 border-b border-[var(--border-subtle)]">
                {ticks.map((tick) => {
                  const left = ((tick - min) / span) * 100;
                  return (
                    <div
                      key={tick}
                      className="absolute top-0 h-full"
                      style={{ left: `${left}%` }}
                    >
                      <div className="h-2 w-px bg-[var(--border-default)]" />
                      <span className="mono absolute -translate-x-1/2 whitespace-nowrap text-[9px] text-[var(--text-tertiary)]">
                        {formatRulerLabel(tick, useTime)}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div
                className="relative h-10 rounded bg-[var(--surface-4)]"
                role="list"
                aria-label={`${channel.label} segment timeline`}
              >
                {sorted.map((seg, index) => {
                  const start = starts[index];
                  const end = ends[index];
                  const left = ((start - min) / span) * 100;
                  const width = Math.max(((end - start) / span) * 100, 1.5);
                  const selected = selectedSegmentId === seg.id;
                  const deleted = segmentDeleted(seg);
                  const prevEnd = index > 0 ? ends[index - 1] : null;
                  const gapStart =
                    prevEnd != null && start > prevEnd
                      ? ((prevEnd - min) / span) * 100
                      : null;
                  const gapWidth =
                    prevEnd != null && start > prevEnd
                      ? ((start - prevEnd) / span) * 100
                      : 0;

                  return (
                    <div key={seg.id}>
                      {gapStart != null && gapWidth > 0.2 ? (
                        <div
                          className="timeline-gap absolute top-1 bottom-1 rounded-sm"
                          style={{
                            left: `${gapStart}%`,
                            width: `${gapWidth}%`,
                          }}
                          title={`gap: ${useTime ? `${Math.round((start - (prevEnd ?? start)) / 1000)}s` : `${formatBytes(start - (prevEnd ?? start))} unrecovered`}`}
                        />
                      ) : null}
                      <button
                        type="button"
                        role="listitem"
                        title={`${seg.offset_time_label ?? formatOffset(seg.offset_start)} · ${formatBytes(segmentSize(seg))}`}
                        onClick={() => onSelect(seg.id)}
                        className={cn(
                          "timeline-bar absolute top-1 bottom-1 min-w-[8px]",
                          selected
                            ? "timeline-bar-active"
                            : deleted
                              ? "timeline-bar-deleted"
                              : "timeline-bar-idle",
                        )}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      />
                    </div>
                  );
                })}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {sorted.map((seg) => {
                  const selected = selectedSegmentId === seg.id;
                  const aiFindings =
                    (seg as { ai_findings?: Array<{ id: string }> })
                      .ai_findings ?? [];
                  return (
                    <button
                      key={seg.id}
                      type="button"
                      onClick={() => {
                        onSelect(seg.id);
                        if (aiFindings.length > 0 && onSelectFinding) {
                          onSelectFinding(seg.id, aiFindings[0].id);
                        }
                      }}
                      className={cn(
                        "rounded border px-2 py-1.5 text-left text-[11px] transition-colors",
                        selected
                          ? "border-[var(--accent-500)] bg-[var(--accent-soft)]"
                          : "border-[var(--border-subtle)] bg-[var(--surface-4)] hover:bg-[var(--surface-3)]",
                      )}
                    >
                      <p
                        className="mono"
                        style={{
                          color: selected
                            ? "var(--accent-500)"
                            : "var(--text-secondary)",
                        }}
                      >
                        {seg.offset_time_label ??
                          formatOffset(seg.offset_start)}
                      </p>
                      <p className="mt-0.5 text-[var(--text-tertiary)]">
                        {formatBytes(segmentSize(seg))}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>
        );
      })}
    </div>
  );
}
