import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Pause, Play } from "lucide-react";
import { api, type Segment, type TimelineChannel } from "@/lib/api";
import { resolveApiUrl } from "@/lib/apiBase";
import { formatOffset } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const DELETED_VALIDATIONS = new Set([
  "honeywell_expired_index",
  "filesystem_deleted_inode",
  "unreferenced_carve",
  "h264_nal_tail",
  "slack_recovered",
]);

const SCRUB_WINDOW_MS = 15_000;

type PlaybackDeckProps = {
  channels: TimelineChannel[];
  deviceId: string;
  driftOffsetSeconds: number;
  playhead: number | null;
  onPlayheadChange: (value: number) => void;
  onSelectSegment: (segmentId: string) => void;
};

type ExportCacheEntry = {
  url: string;
  mediaType: string;
};

type LaneExportWindow = {
  segStart: number;
  fromMs: number;
};

function segmentDeleted(seg: Segment): boolean {
  if ((seg as { deleted_candidate?: boolean }).deleted_candidate) return true;
  const validation = seg.validation ?? "";
  return DELETED_VALIDATIONS.has(validation);
}

function parseSegmentStart(seg: Segment, useTime: boolean): number {
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

function parseSegmentEnd(
  seg: Segment,
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
    return start;
  }
  if (seg.offset_end != null) return seg.offset_end;
  const byteLen = seg.byte_length ?? 1;
  return (seg.offset_start ?? start) + Math.max(byteLen, 1);
}

function formatPlayhead(value: number, useTime: boolean): string {
  if (!useTime) return formatOffset(value);
  return new Date(value).toISOString().replace("T", " ").slice(0, 19);
}

function exportCacheKey(segId: string, fromMs?: number, toMs?: number): string {
  if (fromMs == null || toMs == null) return segId;
  return `${segId}:${fromMs}:${toMs}`;
}

function findSegmentAtPlayhead(
  segments: Segment[],
  playhead: number,
  useTime: boolean,
): Segment | undefined {
  return segments.find((seg) => {
    const start = parseSegmentStart(seg, useTime);
    const end = parseSegmentEnd(seg, start, useTime);
    return playhead >= start && playhead <= end;
  });
}

export function PlaybackDeck({
  channels,
  deviceId,
  driftOffsetSeconds,
  playhead,
  onPlayheadChange,
  onSelectSegment,
}: PlaybackDeckProps) {
  const [playing, setPlaying] = useState(false);
  const exportCacheRef = useRef(new Map<string, ExportCacheEntry>());
  const syncTokenRef = useRef(0);
  const laneExportWindowRef = useRef<Record<number, LaneExportWindow>>({});
  const lastSelectedSegmentRef = useRef<string | null>(null);
  const [laneUrls, setLaneUrls] = useState<Record<number, string>>({});
  const [laneMedia, setLaneMedia] = useState<Record<number, string>>({});
  const [laneGaps, setLaneGaps] = useState<Record<number, boolean>>({});
  const [laneLoading, setLaneLoading] = useState<Record<number, boolean>>({});
  const [laneErrors, setLaneErrors] = useState<Record<number, boolean>>({});
  const videoRefs = useRef<Record<number, HTMLVideoElement | null>>({});
  const rafRef = useRef<number | null>(null);

  const flatSegments = useMemo(
    () =>
      channels.flatMap((ch) =>
        ch.segments.map((seg) => ({ ...seg, channel: ch.channel })),
      ),
    [channels],
  );

  const useTime = useMemo(
    () =>
      flatSegments.some(
        (seg) =>
          !!(
            seg.corrected_start_ts ??
            seg.recorder_start_ts ??
            seg.offset_time_label
          ),
      ),
    [flatSegments],
  );

  const domain = useMemo(() => {
    if (flatSegments.length === 0) return { min: 0, max: 1 };
    const starts = flatSegments.map((s) => parseSegmentStart(s, useTime));
    const ends = flatSegments.map((s, i) =>
      parseSegmentEnd(s, starts[i], useTime),
    );
    return { min: Math.min(...starts), max: Math.max(...ends) };
  }, [flatSegments, useTime]);

  const effectivePlayhead = playhead ?? domain.min;

  const resolveExport = useCallback(
    async (seg: Segment, fromMs?: number, toMs?: number) => {
      const exportCache = exportCacheRef.current;
      const key = exportCacheKey(seg.id, fromMs, toMs);
      const cached = exportCache.get(key);
      if (cached) return cached;
      const result = await api.exportSegment(deviceId, seg.id, {
        fromMs,
        toMs,
      });
      const entry = {
        url: resolveApiUrl(result.download_url),
        mediaType: result.media_type,
      };
      exportCache.set(key, entry);
      return entry;
    },
    [deviceId],
  );

  const segmentAtPlayhead = useCallback(
    (channel: number) => {
      const items = channels.find((c) => c.channel === channel)?.segments ?? [];
      return findSegmentAtPlayhead(items, effectivePlayhead, useTime);
    },
    [channels, effectivePlayhead, useTime],
  );

  const syncSignature = useMemo(() => {
    return channels
      .map((channel) => {
        const seg = findSegmentAtPlayhead(
          channel.segments,
          effectivePlayhead,
          useTime,
        );
        if (!seg) return `${channel.channel}:gap`;
        const start = parseSegmentStart(seg, useTime);
        const bucket = useTime
          ? Math.floor((effectivePlayhead - start) / SCRUB_WINDOW_MS)
          : 0;
        return `${channel.channel}:${seg.id}:${bucket}`;
      })
      .join("|");
  }, [channels, effectivePlayhead, useTime]);

  const stepToNextSegment = useCallback(() => {
    const ordered = [...flatSegments].sort((a, b) => {
      const aStart = parseSegmentStart(a, useTime);
      const bStart = parseSegmentStart(b, useTime);
      return aStart - bStart;
    });
    const current = ordered.find((seg) => {
      const start = parseSegmentStart(seg, useTime);
      return Math.abs(start - effectivePlayhead) < 1;
    });
    const idx = current ? ordered.indexOf(current) : -1;
    const next = ordered[idx + 1] ?? ordered[0];
    if (!next) return;
    onPlayheadChange(parseSegmentStart(next, useTime));
    onSelectSegment(next.id);
  }, [
    effectivePlayhead,
    flatSegments,
    onPlayheadChange,
    onSelectSegment,
    useTime,
  ]);

  useEffect(() => {
    const token = ++syncTokenRef.current;
    let cancelled = false;

    async function syncLanes() {
      const nextUrls: Record<number, string> = {};
      const nextMedia: Record<number, string> = {};
      const nextGaps: Record<number, boolean> = {};
      const nextLoading: Record<number, boolean> = {};

      let primarySegmentId: string | null = null;

      for (const channel of channels) {
        const seg = findSegmentAtPlayhead(
          channel.segments,
          effectivePlayhead,
          useTime,
        );
        if (!seg) {
          nextGaps[channel.channel] = true;
          delete nextUrls[channel.channel];
          delete nextMedia[channel.channel];
          continue;
        }

        nextGaps[channel.channel] = false;
        if (primarySegmentId == null) {
          primarySegmentId = seg.id;
        }

        const start = parseSegmentStart(seg, useTime);
        const end = parseSegmentEnd(seg, start, useTime);
        let fromMs: number | undefined;
        let toMs: number | undefined;
        if (useTime) {
          const relPlayhead = effectivePlayhead - start;
          const bucket = Math.floor(relPlayhead / SCRUB_WINDOW_MS);
          fromMs = Math.max(0, bucket * SCRUB_WINDOW_MS);
          toMs = Math.min(end - start, fromMs + SCRUB_WINDOW_MS * 2);
        }

        const cacheKey = exportCacheKey(seg.id, fromMs, toMs);
        const cached = exportCacheRef.current.get(cacheKey);
        if (cached) {
          nextUrls[channel.channel] = cached.url;
          nextMedia[channel.channel] = cached.mediaType;
          laneExportWindowRef.current[channel.channel] = {
            segStart: start,
            fromMs: fromMs ?? 0,
          };
          continue;
        }

        nextLoading[channel.channel] = true;
        try {
          const exported = await resolveExport(seg, fromMs, toMs);
          if (cancelled || token !== syncTokenRef.current) return;
          nextUrls[channel.channel] = exported.url;
          nextMedia[channel.channel] = exported.mediaType;
          laneExportWindowRef.current[channel.channel] = {
            segStart: start,
            fromMs: fromMs ?? 0,
          };
        } catch {
          if (cancelled || token !== syncTokenRef.current) return;
          nextGaps[channel.channel] = true;
          delete nextUrls[channel.channel];
          delete nextMedia[channel.channel];
        } finally {
          nextLoading[channel.channel] = false;
        }
      }

      if (cancelled || token !== syncTokenRef.current) return;

      if (
        primarySegmentId &&
        primarySegmentId !== lastSelectedSegmentRef.current
      ) {
        lastSelectedSegmentRef.current = primarySegmentId;
        onSelectSegment(primarySegmentId);
      }

      setLaneUrls(nextUrls);
      setLaneMedia(nextMedia);
      setLaneGaps(nextGaps);
      setLaneLoading(nextLoading);
      setLaneErrors({});
    }

    void syncLanes();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync on bucket/segment changes only
  }, [syncSignature, channels, deviceId, resolveExport, onSelectSegment]);

  useEffect(() => {
    if (!useTime) return;
    for (const channel of channels) {
      const window = laneExportWindowRef.current[channel.channel];
      const video = videoRefs.current[channel.channel];
      const url = laneUrls[channel.channel];
      if (!window || !video || !url) continue;
      const offsetSec =
        (effectivePlayhead - window.segStart) / 1000 +
        driftOffsetSeconds -
        window.fromMs / 1000;
      if (
        Number.isFinite(offsetSec) &&
        offsetSec >= 0 &&
        Math.abs(video.currentTime - offsetSec) > 0.2
      ) {
        video.currentTime = offsetSec;
      }
    }
  }, [effectivePlayhead, driftOffsetSeconds, channels, laneUrls, useTime]);

  useEffect(() => {
    if (!playing || !useTime) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    let last = performance.now();
    const tick = (now: number) => {
      const delta = now - last;
      last = now;
      let next = effectivePlayhead + delta;
      if (next >= domain.max) {
        next = domain.min;
      }
      onPlayheadChange(next);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, domain, effectivePlayhead, onPlayheadChange, useTime]);

  useEffect(() => {
    for (const channel of channels) {
      const video = videoRefs.current[channel.channel];
      if (!video) continue;
      const active = segmentAtPlayhead(channel.channel);
      if (playing && active && laneUrls[channel.channel]) {
        void video.play().catch(() => undefined);
      } else {
        video.pause();
      }
    }
  }, [playing, channels, laneUrls, segmentAtPlayhead]);

  if (channels.length === 0) {
    return (
      <section className="visily-card p-6 text-center">
        <p className="text-[14px] font-medium text-[var(--text-primary)]">
          No recovered video lanes yet
        </p>
        <p className="mx-auto mt-2 max-w-md text-[13px] text-[var(--text-secondary)]">
          Run recovery on Step 3 first. Playback appears here when sequences
          with decodable video are indexed — generic disk images may only yield
          filesystem or carve hits without a camera timeline.
        </p>
      </section>
    );
  }

  const gridCols =
    channels.length <= 1
      ? "grid-cols-1"
      : channels.length <= 4
        ? "grid-cols-2"
        : "grid-cols-3";

  return (
    <section className="visily-card space-y-3 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="visily-card-title text-[11px]">Playback deck</p>
          <p className="mono text-[11px] text-[var(--text-tertiary)]">
            {useTime
              ? formatPlayhead(effectivePlayhead, true)
              : "byte-offset order — step through segments"}
          </p>
        </div>
        <div className="flex gap-2">
          {!useTime ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={stepToNextSegment}
              aria-label="Step to next segment"
            >
              Step
              <ChevronRight className="h-4 w-4" />
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setPlaying((value) => !value)}
            aria-label={playing ? "Pause" : "Play"}
            disabled={!useTime}
            title={
              useTime
                ? undefined
                : "Byte-offset mode — use Step to advance between segments"
            }
          >
            {playing ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      <div className={`grid gap-3 ${gridCols}`}>
        {channels.map((channel) => {
          const activeSeg = segmentAtPlayhead(channel.channel);
          const deleted = activeSeg ? segmentDeleted(activeSeg) : false;
          return (
            <div
              key={channel.channel}
              className={`overflow-hidden rounded border ${
                deleted ? "playback-lane-deleted" : ""
              }`}
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <div
                className="flex items-center justify-between border-b px-2 py-1 text-[11px]"
                style={{ borderColor: "var(--border-subtle)" }}
              >
                <span>{channel.label}</span>
                {deleted ? (
                  <span className="font-semibold uppercase tracking-wide text-[var(--status-warning)]">
                    Recovered — unreferenced
                  </span>
                ) : null}
                {laneGaps[channel.channel] ? (
                  <span className="text-[var(--text-tertiary)]">gap</span>
                ) : null}
              </div>
              {laneUrls[channel.channel] && !laneErrors[channel.channel] ? (
                <video
                  ref={(el) => {
                    videoRefs.current[channel.channel] = el;
                  }}
                  className="aspect-video w-full bg-[var(--surface-4)]"
                  src={
                    laneMedia[channel.channel] === "h264"
                      ? `${laneUrls[channel.channel]}${laneUrls[channel.channel].includes("?") ? "&" : "?"}transcode=1`
                      : laneUrls[channel.channel]
                  }
                  muted
                  playsInline
                  onError={() =>
                    setLaneErrors((prev) => ({
                      ...prev,
                      [channel.channel]: true,
                    }))
                  }
                />
              ) : (
                <div className="flex aspect-video items-center justify-center bg-[var(--surface-4)] p-3 text-center text-[12px] text-[var(--text-tertiary)]">
                  {laneErrors[channel.channel]
                    ? "Recovered segment has no decodable video frames — carve produced a non-continuous stream."
                    : laneGaps[channel.channel]
                      ? "No segment at playhead"
                      : laneLoading[channel.channel]
                        ? "Exporting…"
                        : "Preparing playback…"}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <label className="block text-[11px] text-[var(--text-secondary)]">
        Shared transport
        <input
          type="range"
          min={domain.min}
          max={domain.max}
          step={useTime ? 1000 : 1}
          value={effectivePlayhead}
          onChange={(e) => {
            setPlaying(false);
            onPlayheadChange(Number(e.target.value));
          }}
          className="mt-1 w-full"
        />
      </label>
    </section>
  );
}
