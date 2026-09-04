import { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type Segment, type TimelineChannel } from "@/lib/api";
import { TimelineView } from "@/components/TimelineView";
import { PlaybackDeck } from "@/components/PlaybackDeck";
import { VirtualTable } from "@/components/ui/virtual-table";
import { Button } from "@/components/ui/button";
import { resolveApiUrl } from "@/lib/apiBase";
import { formatBytes, formatOffset } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";
import { FindingsTrack } from "@/components/forensic/FindingsTrack";
import { SegmentInspector } from "@/components/forensic/SegmentInspector";
import { PageHeader } from "@/components/visily/PageHeader";

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

export function CaseTimelinePage() {
  const { caseId, workspace } = useCaseContext();
  const [deviceId, setDeviceId] = useState("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [channels, setChannels] = useState<TimelineChannel[]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(
    null,
  );
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [wallUnix, setWallUnix] = useState("");
  const [deviceUnix, setDeviceUnix] = useState("");
  const [driftOffset, setDriftOffset] = useState<number | null>(null);
  const [normalization, setNormalization] = useState<{
    method: string;
    rtc_parsed: boolean;
    note: string;
  } | null>(null);

  const evidenceList = workspace?.evidence ?? [];
  const deviceDrift = driftOffset ?? 0;

  const useTime = useMemo(
    () =>
      channels.some((channel) =>
        channel.segments.some(
          (seg) =>
            !!(
              seg.corrected_start_ts ??
              seg.recorder_start_ts ??
              seg.offset_time_label
            ),
        ),
      ),
    [channels],
  );

  useEffect(() => {
    if (evidenceList[0] && !deviceId) {
      setDeviceId(evidenceList[0].id);
    }
  }, [evidenceList, deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    void api.listDeviceSegments(deviceId).then((d) => setSegments(d.segments));
    void api
      .getTimeline(caseId, deviceId)
      .then((d) => {
        setChannels(d.channels);
        setNormalization(d.normalization ?? null);
        const first = d.channels.flatMap((channel) => channel.segments)[0];
        if (first) {
          const timeMode = d.channels.some((channel) =>
            channel.segments.some(
              (seg) =>
                !!(
                  seg.corrected_start_ts ??
                  seg.recorder_start_ts ??
                  seg.offset_time_label
                ),
            ),
          );
          setPlayhead(parseSegmentStart(first, timeMode));
          setSelectedSegmentId(first.id);
        }
      })
      .catch(() => {
        setChannels([]);
        setNormalization(null);
      });
  }, [deviceId, caseId]);

  const seekToSegment = useCallback(
    (segmentId: string) => {
      setSelectedSegmentId(segmentId);
      const seg = channels
        .flatMap((channel) => channel.segments)
        .find((item) => item.id === segmentId);
      if (seg) {
        setPlayhead(parseSegmentStart(seg, useTime));
      }
    },
    [channels, useTime],
  );

  async function handleExport(segmentId: string) {
    if (!deviceId) return;
    try {
      const result = await api.exportSegment(deviceId, segmentId);
      window.open(
        resolveApiUrl(result.download_url),
        "_blank",
        "noopener,noreferrer",
      );
      toast.success("Segment exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed", {
        duration: Infinity,
      });
    }
  }

  async function handleDriftCalibration() {
    if (!deviceId || !wallUnix || !deviceUnix) {
      toast.error("Enter wall-clock and device reference Unix timestamps");
      return;
    }
    try {
      const result = await api.calibrateDrift(
        deviceId,
        Number(wallUnix),
        Number(deviceUnix),
      );
      setDriftOffset(result.drift_offset_seconds);
      toast.success(
        `Drift offset ${result.drift_offset_seconds.toFixed(1)}s stored`,
        { description: result.note },
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Calibration failed", {
        duration: Infinity,
      });
    }
  }

  const selectedSegment = useMemo(
    () => segments.find((s) => s.id === selectedSegmentId) ?? null,
    [segments, selectedSegmentId],
  );

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        kicker="Temporal review"
        title="Recovery timeline"
        subtitle="Multi-camera playback deck with shared transport. Deleted recoveries are highlighted on each lane."
      />

      <section className="visily-card p-3">
        <label className="label">Evidence device</label>
        {evidenceList.length === 0 ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            No evidence.{" "}
            <Link
              to={`/cases/${caseId}/acquire`}
              className="text-[var(--accent-500)] underline"
            >
              Acquire
            </Link>{" "}
            first.
          </p>
        ) : (
          <select
            className="field max-w-md"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
          >
            <option value="">Select device</option>
            {evidenceList.map((e) => (
              <option key={e.id} value={e.id}>
                {e.filename}
              </option>
            ))}
          </select>
        )}
      </section>

      {deviceId ? (
        <section className="visily-card space-y-2 p-3">
          <p className="visily-card-title text-[11px]">
            Clock drift calibration
          </p>
          {normalization ? (
            <div className="space-y-0.5">
              <p
                className={`text-[12px] font-medium ${
                  normalization.rtc_parsed
                    ? "text-[var(--status-success)]"
                    : "text-[var(--status-warning)]"
                }`}
              >
                {normalization.rtc_parsed
                  ? "Recorder clock found — timeline is time-ordered."
                  : "No recorder clock found — timeline is byte-offset order only, not wall-clock time."}
              </p>
              <p className="mono text-[10px] text-[var(--text-tertiary)]">
                {normalization.note}
              </p>
            </div>
          ) : null}
          <p className="text-[12px] text-[var(--text-tertiary)]">
            Supply one known event: wall-clock Unix time and the same moment on
            the DVR clock.
          </p>
          <div className="grid max-w-lg gap-2 sm:grid-cols-2">
            <input
              className="field mono"
              placeholder="Wall Unix (e.g. 1700000000)"
              value={wallUnix}
              onChange={(e) => setWallUnix(e.target.value)}
            />
            <input
              className="field mono"
              placeholder="Device Unix"
              value={deviceUnix}
              onChange={(e) => setDeviceUnix(e.target.value)}
            />
          </div>
          <Button size="sm" onClick={() => void handleDriftCalibration()}>
            Apply offset
          </Button>
          {driftOffset !== null ? (
            <p className="mono text-[12px] text-[var(--text-secondary)]">
              Stored offset: {driftOffset.toFixed(3)}s
            </p>
          ) : null}
        </section>
      ) : null}

      {deviceId && channels.length === 0 ? (
        <section className="visily-card p-6 text-center">
          <p className="text-[14px] font-medium text-[var(--text-primary)]">
            Timeline empty
          </p>
          <p className="mx-auto mt-2 max-w-lg text-[13px] text-[var(--text-secondary)]">
            Recovery has not produced indexed sequences for this device, or the
            image has no vendor DVR structure (e.g. a camera-card E01). Complete{" "}
            <Link
              to={`/cases/${caseId}/recover`}
              className="text-[var(--accent-500)] underline"
            >
              recovery
            </Link>{" "}
            on DVR/NVR media to unlock multi-channel playback.
          </p>
        </section>
      ) : null}

      {deviceId && channels.length > 0 ? (
        <>
          <TimelineView
            channels={channels}
            selectedSegmentId={selectedSegmentId}
            onSelect={seekToSegment}
            onSelectFinding={(segmentId) => seekToSegment(segmentId)}
          />
          <FindingsTrack
            channels={channels}
            useTime={useTime}
            selectedSegmentId={selectedSegmentId}
            onSelectSegment={seekToSegment}
          />
          <PlaybackDeck
            channels={channels}
            deviceId={deviceId}
            driftOffsetSeconds={deviceDrift}
            playhead={playhead}
            onPlayheadChange={setPlayhead}
            onSelectSegment={setSelectedSegmentId}
          />
          <SegmentInspector
            caseId={caseId}
            deviceId={deviceId}
            segment={selectedSegment}
            variant="timeline"
          />
          <section className="visily-card overflow-hidden">
            <div className="visily-card-header">
              <span className="visily-card-title">Sequences</span>
              <span className="mono text-[10px] text-[var(--text-tertiary)]">
                {segments.length} total
              </span>
            </div>
            <VirtualTable
              rows={segments}
              maxHeight={360}
              emptyMessage="No sequences recovered."
              columns={[
                { key: "ch", header: "Ch", cell: (seg) => seg.channel ?? "—" },
                {
                  key: "start",
                  header: "Byte start",
                  className: "mono",
                  cell: (seg) =>
                    seg.offset_start != null
                      ? formatOffset(seg.offset_start)
                      : "—",
                },
                {
                  key: "rec",
                  header: "Recorder",
                  className: "mono text-[11px]",
                  cell: (seg) => seg.recorder_start_ts ?? "—",
                },
                {
                  key: "corr",
                  header: "Corrected",
                  className: "mono text-[11px]",
                  cell: (seg) => seg.corrected_start_ts ?? "—",
                },
                {
                  key: "source",
                  header: "Source",
                  className: "text-[10px]",
                  cell: (seg) => formatTimestampSource(seg.timestamp_source),
                },
                {
                  key: "size",
                  header: "Size",
                  className: "mono",
                  cell: (seg) =>
                    formatBytes(
                      seg.byte_length ??
                        (seg.offset_end ?? 0) - (seg.offset_start ?? 0),
                    ),
                },
                {
                  key: "export",
                  header: "",
                  cell: (seg) => (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => void handleExport(seg.id)}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                  ),
                },
              ]}
            />
          </section>
        </>
      ) : null}
    </div>
  );
}
