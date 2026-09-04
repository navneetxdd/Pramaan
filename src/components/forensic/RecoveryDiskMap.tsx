import { useMemo } from "react";
import type { Segment } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import {
  allocationDetail,
  allocationLabel,
  allocationOf,
  type AllocationState,
} from "@/lib/allocation";
import { cn } from "@/lib/utils";

/**
 * Where recovered recordings physically sit in the evidence image.
 *
 * This is a byte-offset view, not a time view — the Timeline menu owns time.
 * It answers questions an examiner actually asks of a recovery run: is the
 * footage clustered or scattered, how much of the image did we account for, and
 * where does the deleted recording sit relative to the live ones.
 *
 * Every rectangle is drawn from the parser's real `byte_offset` / `byte_length`
 * against the evidence file's real `size_bytes`. Nothing is scaled to look
 * fuller than it is: the unpainted background is genuinely unrecovered space.
 */

function lengthOf(segment: Segment): number {
  return (
    segment.byte_length ??
    (segment.offset_end ?? 0) - (segment.offset_start ?? 0)
  );
}

const STATE_COLOR: Record<AllocationState, string> = {
  allocated: "var(--status-success)",
  deleted: "var(--status-danger)",
  recording: "var(--status-info)",
  unknown: "var(--text-tertiary)",
};

type DiskMapProps = {
  segments: Segment[];
  imageSize: number;
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
  /** True while the engine is actually scanning — drives the read-head sweep. */
  scanning?: boolean;
};

export function RecoveryDiskMap({
  segments,
  imageSize,
  selectedSegmentId,
  onSelect,
  scanning = false,
}: DiskMapProps) {
  const lanes = useMemo(() => {
    const byChannel = new Map<number, Segment[]>();
    for (const segment of segments) {
      const channel = segment.channel ?? 0;
      const list = byChannel.get(channel);
      if (list) list.push(segment);
      else byChannel.set(channel, [segment]);
    }
    return [...byChannel.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([channel, rows]) => {
        const ordered = [...rows].sort(
          (a, b) => (a.offset_start ?? 0) - (b.offset_start ?? 0),
        );
        const bytes = ordered.reduce((t, s) => t + lengthOf(s), 0);
        // Unrecovered space between consecutive recoveries on this channel.
        // A gap is where overwritten or unparsed footage would sit.
        let gaps = 0;
        for (let i = 1; i < ordered.length; i += 1) {
          const prevEnd =
            (ordered[i - 1].offset_start ?? 0) + lengthOf(ordered[i - 1]);
          if ((ordered[i].offset_start ?? 0) > prevEnd) gaps += 1;
        }
        return { channel, rows: ordered, bytes, gaps };
      });
  }, [segments]);

  const recoveredBytes = useMemo(
    () => segments.reduce((total, s) => total + lengthOf(s), 0),
    [segments],
  );

  const statesPresent = useMemo(() => {
    const set = new Set<AllocationState>();
    for (const segment of segments) set.add(allocationOf(segment));
    return [...set];
  }, [segments]);

  if (segments.length === 0 || imageSize <= 0) {
    return (
      <p className="px-4 py-6 text-[12px] text-[var(--text-tertiary)]">
        The disk map appears once recovery has recovered at least one recording.
      </p>
    );
  }

  const coveragePct = (recoveredBytes / imageSize) * 100;
  // A recording thinner than the 3px floor is drawn wider than it really is.
  // Say so, rather than let the map imply more coverage than exists.
  const anyBelowScale = segments.some((s) => lengthOf(s) / imageSize < 0.004);
  // Sub-0.1% coverage is real and common on a large image; never round it to 0.
  const coverageLabel =
    coveragePct >= 0.1 ? `${coveragePct.toFixed(1)}%` : "<0.1%";

  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-[12px] text-[var(--text-secondary)]">
          <span className="mono font-medium text-[var(--text-primary)]">
            {formatBytes(recoveredBytes)}
          </span>{" "}
          recovered from <span className="mono">{formatBytes(imageSize)}</span>{" "}
          image
          <span className="text-[var(--text-tertiary)]">
            {" "}
            · {coverageLabel} of the image accounted for
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          {statesPresent.map((state) => (
            <span key={state} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-[2px]"
                style={{ background: STATE_COLOR[state] }}
              />
              <span className="text-[var(--text-secondary)]">
                {allocationLabel(state)}
              </span>
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-[2px] border border-[var(--border-default)] bg-[var(--surface-4)]" />
            <span className="text-[var(--text-tertiary)]">Not recovered</span>
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        {lanes.map(({ channel, rows: laneSegments, bytes, gaps }) => (
          <div key={channel} className="flex items-center gap-2">
            <span className="w-28 shrink-0 text-right text-[10px] leading-tight text-[var(--text-tertiary)]">
              <span className="mono uppercase text-[var(--text-secondary)]">
                Ch {channel}
              </span>
              <br />
              {laneSegments.length} rec · {formatBytes(bytes)}
              {gaps > 0 ? ` · ${gaps} gap${gaps > 1 ? "s" : ""}` : ""}
            </span>
            <div
              className={cn(
                "rec-lane rec-platter relative h-7 min-w-0 flex-1 overflow-hidden rounded-[3px] border border-[var(--border-subtle)]",
                scanning ? "is-scanning" : "",
              )}
            >
              {laneSegments.map((segment) => {
                const start = segment.offset_start ?? 0;
                const length =
                  segment.byte_length ?? (segment.offset_end ?? 0) - start;
                const state = allocationOf(segment);
                const selected = segment.id === selectedSegmentId;
                return (
                  <button
                    key={segment.id}
                    type="button"
                    onClick={() => onSelect(segment.id)}
                    title={`${allocationLabel(state)} · ${formatBytes(length)} @ 0x${start.toString(16)}\n${allocationDetail(segment)}`}
                    aria-label={`Channel ${channel}, ${allocationLabel(state)} recording of ${formatBytes(length)} at offset ${start}`}
                    className={cn(
                      "rec-extent absolute top-0 h-full rounded-[1px] transition-opacity hover:opacity-80",
                      selected
                        ? "ring-2 ring-inset ring-[var(--accent-500)]"
                        : "",
                    )}
                    style={{
                      left: `${(start / imageSize) * 100}%`,
                      // Floor the width so a small recording stays clickable
                      // instead of collapsing to an invisible sliver.
                      width: `max(3px, ${(length / imageSize) * 100}%)`,
                      background: STATE_COLOR[state],
                    }}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        {/* Must match the lane label width or the axis lies about position. */}
        <span className="w-28 shrink-0" />
        <div className="rec-ruler relative h-4 min-w-0 flex-1">
          {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
            <span
              key={fraction}
              className="mono absolute top-0 text-[9px] text-[var(--text-tertiary)]"
              style={{
                left: `${fraction * 100}%`,
                transform:
                  fraction === 0
                    ? "none"
                    : fraction === 1
                      ? "translateX(-100%)"
                      : "translateX(-50%)",
              }}
            >
              {formatBytes(imageSize * fraction)}
            </span>
          ))}
        </div>
      </div>

      {anyBelowScale ? (
        <p className="pt-1 text-[10px] text-[var(--text-tertiary)]">
          Positions are to scale. Recordings narrower than 3&nbsp;px are drawn
          at 3&nbsp;px so they stay visible and clickable, so the coloured area
          overstates coverage — read the figure above, not the bar.
        </p>
      ) : null}
    </div>
  );
}
