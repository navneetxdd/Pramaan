import type { TimelineChannel } from "@/lib/api";
import { cn, formatOffset } from "@/lib/utils";

type FindingsTrackProps = {
  channels: TimelineChannel[];
  useTime: boolean;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
};

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

const FINDING_COLORS: Record<string, string> = {
  motion: "var(--status-warning)",
  face: "var(--accent-500)",
  object: "var(--status-info)",
};

export function FindingsTrack({
  channels,
  useTime,
  selectedSegmentId,
  onSelectSegment,
}: FindingsTrackProps) {
  const items = channels.flatMap((channel) =>
    channel.segments.flatMap((seg) => {
      const aiFindings =
        (
          seg as {
            ai_findings?: Array<{
              id: string;
              finding_type: string;
              frame_offset_ms: number;
              label?: string;
            }>;
          }
        ).ai_findings ?? [];
      const base = parseStart(seg, useTime);
      return aiFindings.map((finding) => ({
        ...finding,
        segmentId: seg.id,
        at: base + finding.frame_offset_ms,
      }));
    }),
  );

  if (items.length === 0) return null;

  const min = Math.min(...items.map((i) => i.at));
  const max = Math.max(...items.map((i) => i.at), min + 1);
  const span = Math.max(max - min, 1);

  return (
    <section className="visily-card overflow-hidden">
      <div className="panel-header">
        <span className="panel-title">Motion / AI findings</span>
        <span className="mono">{items.length} events</span>
      </div>
      <div className="relative h-10 rounded bg-[var(--surface-4)] m-3">
        {items.map((item) => {
          const left = ((item.at - min) / span) * 100;
          const selected = selectedSegmentId === item.segmentId;
          return (
            <button
              key={item.id}
              type="button"
              title={`${item.finding_type}${item.label ? `: ${item.label}` : ""}`}
              onClick={() => onSelectSegment(item.segmentId)}
              className={cn(
                "absolute top-1 bottom-1 w-2 rounded-sm",
                selected ? "ring-2 ring-[var(--accent-500)]" : "",
              )}
              style={{
                left: `${left}%`,
                background:
                  FINDING_COLORS[item.finding_type] ?? "var(--text-tertiary)",
              }}
            />
          );
        })}
      </div>
      <p className="px-3 pb-3 text-[10px] text-[var(--text-tertiary)]">
        {items.length} marker{items.length === 1 ? "" : "s"} on the timeline's
        shared axis
        {useTime
          ? " (wall/recorder time)"
          : ` (${formatOffset(min)}–${formatOffset(max)})`}
        .
      </p>
    </section>
  );
}
