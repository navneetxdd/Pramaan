import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type Segment } from "@/lib/api";
import { TimelineView } from "@/components/TimelineView";
import { VideoPreview } from "@/components/VideoPreview";
import { Button } from "@/components/ui/button";
import { resolveApiUrl } from "@/lib/apiBase";
import { formatBytes, formatOffset } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";

export function CaseTimelinePage() {
  const { caseId, workspace } = useCaseContext();
  const navigate = useNavigate();
  const [deviceId, setDeviceId] = useState("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [channels, setChannels] = useState<Awaited<ReturnType<typeof api.getTimeline>>["channels"]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMedia, setPreviewMedia] = useState("video/mp4");
  const [wallUnix, setWallUnix] = useState("");
  const [deviceUnix, setDeviceUnix] = useState("");
  const [driftOffset, setDriftOffset] = useState<number | null>(null);

  const evidenceList = workspace?.evidence ?? [];

  useEffect(() => {
    if (evidenceList[0] && !deviceId) {
      setDeviceId(evidenceList[0].id);
    }
  }, [evidenceList, deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    void api.listDeviceSegments(deviceId).then((d) => setSegments(d.segments));
    void api.getTimeline(caseId, deviceId).then((d) => setChannels(d.channels)).catch(() => setChannels([]));
  }, [deviceId, caseId]);

  async function handleExport(segmentId: string) {
    if (!deviceId) return;
    try {
      const result = await api.exportSegment(deviceId, segmentId);
      setPreviewUrl(resolveApiUrl(result.download_url));
      setPreviewMedia(result.media_type);
      toast.success("Segment exported");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed", { duration: Infinity });
    }
  }

  async function handleDriftCalibration() {
    if (!deviceId || !wallUnix || !deviceUnix) {
      toast.error("Enter wall-clock and device reference Unix timestamps");
      return;
    }
    try {
      const result = await api.calibrateDrift(deviceId, Number(wallUnix), Number(deviceUnix));
      setDriftOffset(result.drift_offset_seconds);
      toast.success(`Drift offset ${result.drift_offset_seconds.toFixed(1)}s stored`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Calibration failed", { duration: Infinity });
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1]">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Temporal review</p>
          <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Recovery timeline</h1>
          <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
            Channel-aligned segment bars from completed recovery jobs. Export segments for preview playback.
          </p>
        </div>
      </div>

      <section className="visily-card p-3">
        <label className="label">Evidence device</label>
        {evidenceList.length === 0 ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            No evidence. <Link to={`/cases/${caseId}/acquire`} className="text-[var(--accent-500)] underline">Acquire</Link> first.
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
          <p className="visily-card-title text-[11px]">Clock drift calibration</p>
          <p className="text-[12px] text-[var(--text-tertiary)]">
            Supply one known event: wall-clock Unix time and the same moment on the DVR clock.
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
            <p className="mono text-[12px] text-[var(--text-secondary)]">Stored offset: {driftOffset.toFixed(3)}s</p>
          ) : null}
        </section>
      ) : null}

      {deviceId ? (
        <>
          <TimelineView
            channels={channels}
            selectedSegmentId={selectedSegmentId}
            onSelect={setSelectedSegmentId}
            onSelectFinding={() => navigate(`/cases/${caseId}/ai-analytics`)}
          />
          {previewUrl ? <VideoPreview src={previewUrl} mediaType={previewMedia} /> : null}
          <section className="visily-card overflow-hidden">
            <div className="visily-card-header">
              <span className="visily-card-title">Sequences</span>
              <span className="mono text-[10px] text-[var(--text-tertiary)]">{segments.length} total</span>
            </div>
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>Ch</th>
                  <th>Byte start</th>
                  <th>Recorder</th>
                  <th>Corrected</th>
                  <th>Source</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {segments.map((seg) => (
                  <tr key={seg.id} className={selectedSegmentId === seg.id ? "row-selected" : ""}>
                    <td>{seg.channel ?? "—"}</td>
                    <td className="mono">{seg.offset_start != null ? formatOffset(seg.offset_start) : "—"}</td>
                    <td className="mono text-[11px]">{seg.recorder_start_ts ?? "—"}</td>
                    <td className="mono text-[11px]">{seg.corrected_start_ts ?? "—"}</td>
                    <td className="text-[10px]">{formatTimestampSource(seg.timestamp_source)}</td>
                    <td className="mono">{formatBytes(seg.byte_length ?? (seg.offset_end ?? 0) - (seg.offset_start ?? 0))}</td>
                    <td>
                      <Button variant="ghost" size="icon" onClick={() => void handleExport(seg.id)}>
                        <Download className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </div>
  );
}
