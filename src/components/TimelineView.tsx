import type { TimelineChannel } from "@/lib/api";
import { formatBytes, formatOffset, cn } from "@/lib/utils";

type TimelineViewProps = {
  channels: TimelineChannel[];
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
  onSelectFinding?: (segmentId: string, findingId: string) => void;
};

function segmentSize(seg: TimelineChannel["segments"][0]) {
  return seg.byte_length ?? Math.max(seg.offset_end - seg.offset_start, 1);
}

function parseStart(seg: TimelineChannel["segments"][0], useTime: boolean): number {
  if (useTime) {
    const raw = seg.corrected_start_ts ?? seg.recorder_start_ts ?? seg.offset_time_label;
    if (raw) {
      if (/^\d+(\.\d+)?$/.test(raw)) return Number(raw) * 1000;
      const parsed = Date.parse(raw);
      if (!Number.isNaN(parsed)) return parsed;
    }
  }
  return seg.offset_start ?? seg.offset_order ?? 0;
}

function parseEnd(seg: TimelineChannel["segments"][0], start: number, useTime: boolean): number {
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
  return ["honeywell_expired_index", "filesystem_deleted_inode", "unreferenced_carve", "h264_nal_tail", "slack_recovered"].includes(
    seg.validation ?? "",
  );
}

function formatRulerLabel(value: number, useTime: boolean): string {
  if (!useTime) return formatOffset(value);
  return new Date(value).toISOString().replace("T", " ").slice(11, 19);
}

function buildTicks(min: number, max: number, useTime: boolean): number[] {
  const span = Math.max(max - min, 1);
  const count = 5;
  return Array.from({ length: count + 1 }, (_, index) => min + (span * index) / count);
}

export function TimelineView({ channels, selectedSegmentId, onSelect, onSelectFinding }: TimelineViewProps) {
  if (channels.length === 0) {
    return <p className="text-[13px] text-[var(--text-tertiary)]">No segments recovered.</p>;
  }

  const useTime = channels.some((channel) =>
    channel.segments.some((seg) => !!(seg.corrected_start_ts ?? seg.recorder_start_ts ?? seg.offset_time_label)),
  );

  return (
    <div className="space-y-3">
      {!useTime ? (
        <p className="rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2 font-mono text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
          Byte-offset order (no recorder clock recovered)
        </p>
      ) : null}

      {channels.map((channel) => {
        const sorted = [...channel.segments].sort((a, b) => parseStart(a, useTime) - parseStart(b, useTime));
        const starts = sorted.map((seg) => parseStart(seg, useTime));
        const ends = sorted.map((seg, index) => parseEnd(seg, starts[index], useTime));
        const min = starts.length ? Math.min(...starts) : 0;
        const max = ends.length ? Math.max(...ends) : 1;
        const span = Math.max(max - min, 1);
        const ticks = buildTicks(min, max, useTime);

        return (
          <section key={channel.channel} className="visily-card overflow-hidden">
            <div className="panel-header">
              <span className="panel-title">{channel.label}</span>
              <span className="mono">
                {channel.segment_count} segments · {formatBytes(sorted.reduce((sum, seg) => sum + segmentSize(seg), 0))}
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div className="relative h-6 border-b border-[var(--border-subtle)]">
                {ticks.map((tick) => {
                  const left = ((tick - min) / span) * 100;
                  return (
                    <div key={tick} className="absolute top-0 h-full" style={{ left: `${left}%` }}>
                      <div className="h-2 w-px bg-[var(--border-default)]" />
                      <span className="mono absolute -translate-x-1/2 whitespace-nowrap text-[9px] text-[var(--text-tertiary)]">
                        {formatRulerLabel(tick, useTime)}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="relative h-10 rounded bg-[var(--surface-4)]" role="list" aria-label={`${channel.label} segment timeline`}>
                {sorted.map((seg, index) => {
                  const start = starts[index];
                  const end = ends[index];
                  const left = ((start - min) / span) * 100;
                  const width = Math.max(((end - start) / span) * 100, 1.5);
                  const selected = selectedSegmentId === seg.id;
                  const deleted = segmentDeleted(seg);
                  const prevEnd = index > 0 ? ends[index - 1] : null;
                  const gapStart = prevEnd != null && start > prevEnd ? ((prevEnd - min) / span) * 100 : null;
                  const gapWidth = prevEnd != null && start > prevEnd ? ((start - prevEnd) / span) * 100 : 0;

                  return (
                    <div key={seg.id}>
                      {gapStart != null && gapWidth > 0.2 ? (
                        <div
                          className="timeline-gap absolute top-1 bottom-1 rounded-sm"
                          style={{ left: `${gapStart}%`, width: `${gapWidth}%` }}
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
                          selected ? "timeline-bar-active" : deleted ? "timeline-bar-deleted" : "timeline-bar-idle",
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
                  const aiFindings = (seg as { ai_findings?: Array<{ id: string }> }).ai_findings ?? [];
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
                      <p className="mono" style={{ color: selected ? "var(--accent-500)" : "var(--text-secondary)" }}>
                        {seg.offset_time_label ?? formatOffset(seg.offset_start)}
                      </p>
                      <p className="mt-0.5 text-[var(--text-tertiary)]">{formatBytes(segmentSize(seg))}</p>
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
