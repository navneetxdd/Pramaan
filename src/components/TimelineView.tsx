import type { TimelineChannel } from "@/lib/api";
import { formatBytes, formatOffset, cn } from "@/lib/utils";

type TimelineViewProps = {
  channels: TimelineChannel[];
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
  onSelectFinding?: (segmentId: string, findingId: string) => void;
};

function segmentSize(seg: TimelineChannel["segments"][0]) {
  return seg.byte_length ?? seg.offset_end - seg.offset_start;
}

export function TimelineView({ channels, selectedSegmentId, onSelect, onSelectFinding }: TimelineViewProps) {
  if (channels.length === 0) {
    return <p className="text-[13px] text-[var(--text-tertiary)]">No segments recovered.</p>;
  }

  return (
    <div className="space-y-3">
      {channels.map((channel) => {
        const maxBytes = Math.max(...channel.segments.map(segmentSize), 1);
        const totalBytes = channel.segments.reduce((sum, seg) => sum + segmentSize(seg), 0);

        return (
          <section key={channel.channel} className="visily-card overflow-hidden">
            <div className="panel-header">
              <span className="panel-title">{channel.label}</span>
              <span className="mono">
                {channel.segment_count} segments · {formatBytes(totalBytes)}
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div
                className="flex h-9 items-end gap-0.5 rounded px-2 py-1.5"
                style={{ background: "var(--surface-4)" }}
                role="list"
                aria-label={`${channel.label} segment timeline`}
              >
                {channel.segments.map((seg) => {
                  const bytes = segmentSize(seg);
                  const widthPct = Math.max(8, (bytes / maxBytes) * 100);
                  const selected = selectedSegmentId === seg.id;

                  return (
                    <button
                      key={seg.id}
                      type="button"
                      role="listitem"
                      title={`${seg.offset_time_label ?? formatOffset(seg.offset_start)} · ${formatBytes(bytes)}`}
                      onClick={() => onSelect(seg.id)}
                      className={cn(
                        "timeline-bar group relative min-w-[10px]",
                        selected ? "timeline-bar-active" : "timeline-bar-idle",
                      )}
                      style={{ flex: `${widthPct} 1 0` }}
                    >
                      <span className="timeline-bar-tooltip">
                        {seg.offset_time_label ?? formatOffset(seg.offset_start)}
                        {(seg as { ai_findings?: Array<{ id: string; finding_type: string }> }).ai_findings?.length
                          ? ` · ${(seg as { ai_findings?: Array<unknown> }).ai_findings?.length} AI`
                          : ""}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {channel.segments.map((seg) => {
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
