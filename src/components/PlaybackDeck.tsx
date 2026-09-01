import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
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
    return start + 5000;
  }
  const byteLen =
    seg.byte_length ?? (seg.offset_end ?? start) - (seg.offset_start ?? start);
  return start + Math.max(byteLen, 1);
}

function formatPlayhead(value: number, useTime: boolean): string {
  if (!useTime) return formatOffset(value);
  return new Date(value).toISOString().replace("T", " ").slice(0, 19);
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
  const [exportCache] = useState(() => new Map<string, ExportCacheEntry>());
  const [laneUrls, setLaneUrls] = useState<Record<number, string>>({});
  const [laneMedia, setLaneMedia] = useState<Record<number, string>>({});
  const [laneGaps, setLaneGaps] = useState<Record<number, boolean>>({});
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
    async (segId: string) => {
      const cached = exportCache.get(segId);
      if (cached) return cached;
      const result = await api.exportSegment(deviceId, segId);
      const entry = {
        url: resolveApiUrl(result.download_url),
        mediaType: result.media_type,
      };
      exportCache.set(segId, entry);
      return entry;
    },
    [deviceId, exportCache],
  );

  const segmentAtPlayhead = useCallback(
    (channel: number) => {
      const items = channels.find((c) => c.channel === channel)?.segments ?? [];
      return items.find((seg) => {
        const start = parseSegmentStart(seg, useTime);
        const end = parseSegmentEnd(seg, start, useTime);
        return effectivePlayhead >= start && effectivePlayhead <= end;
      });
    },
    [channels, effectivePlayhead, useTime],
  );

  useEffect(() => {
    let cancelled = false;
    async function syncLanes() {
      const nextUrls: Record<number, string> = {};
      const nextMedia: Record<number, string> = {};
      const nextGaps: Record<number, boolean> = {};
      for (const channel of channels) {
        const seg = segmentAtPlayhead(channel.channel);
        if (!seg) {
          nextGaps[channel.channel] = true;
          continue;
        }
        nextGaps[channel.channel] = false;
        onSelectSegment(seg.id);
        try {
          const exported = await resolveExport(seg.id);
          if (cancelled) return;
          nextUrls[channel.channel] = exported.url;
          nextMedia[channel.channel] = exported.mediaType;
          const start = parseSegmentStart(seg, useTime);
          const video = videoRefs.current[channel.channel];
          if (video) {
            const offsetSec = useTime
              ? (effectivePlayhead - start) / 1000 + driftOffsetSeconds
              : 0;
            if (video.src !== exported.url) {
              video.src = exported.url;
            }
            if (Number.isFinite(offsetSec) && offsetSec >= 0) {
              video.currentTime = offsetSec;
            }
          }
        } catch {
          nextGaps[channel.channel] = true;
        }
      }
      if (!cancelled) {
        setLaneUrls(nextUrls);
        setLaneMedia(nextMedia);
        setLaneGaps(nextGaps);
      }
    }
    void syncLanes();
    return () => {
      cancelled = true;
    };
  }, [
    channels,
    deviceId,
    driftOffsetSeconds,
    effectivePlayhead,
    onSelectSegment,
    resolveExport,
    segmentAtPlayhead,
    useTime,
  ]);

  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    let last = performance.now();
    const tick = (now: number) => {
      const delta = now - last;
      last = now;
      const span = domain.max - domain.min || 1;
      const step = useTime ? delta : span * 0.02;
      let next = effectivePlayhead + step;
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
  }, [playing, channels, laneUrls, segmentAtPlayhead, effectivePlayhead]);

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
              : "byte-offset order — no recorder clock"}
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setPlaying((value) => !value)}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
        </Button>
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
              {laneUrls[channel.channel] ? (
                <video
                  ref={(el) => {
                    videoRefs.current[channel.channel] = el;
                  }}
                  className="aspect-video w-full bg-black"
                  src={
                    laneMedia[channel.channel] === "h264"
                      ? `${laneUrls[channel.channel]}${laneUrls[channel.channel].includes("?") ? "&" : "?"}transcode=1`
                      : laneUrls[channel.channel]
                  }
                  muted
                  playsInline
                />
              ) : (
                <div className="flex aspect-video items-center justify-center bg-[var(--surface-4)] text-[12px] text-[var(--text-tertiary)]">
                  {laneGaps[channel.channel]
                    ? "No segment at playhead"
                    : "Exporting…"}
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
