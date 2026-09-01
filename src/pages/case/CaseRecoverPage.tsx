import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type Segment } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfidenceBadge } from "@/components/forensic/ConfidenceBadge";
import { subscribeJobEvents } from "@/lib/sse";
import { useActivity } from "@/context/ActivityContext";
import { formatBytes } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";

function tierOf(seg: Segment) {
  return (
    seg.confidence_tier ??
    (seg.validation?.includes("_4") || seg.confidence >= 0.85 ? "high" : seg.confidence >= 0.5 ? "medium" : "low")
  );
}

export function CaseRecoverPage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [deviceId, setDeviceId] = useState("");
  const [actor, setActor] = useState(workspace?.case.examiner_name ?? "");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const { setWorking, setIdle } = useActivity();

  useEffect(() => {
    if (workspace?.evidence[0] && !deviceId) setDeviceId(workspace.evidence[0].id);
  }, [workspace, deviceId]);

  useEffect(() => {
    if (!deviceId) {
      setSegments([]);
      return;
    }
    void api
      .listDeviceSegments(deviceId)
      .then((r) => setSegments(r.segments))
      .catch(() => setSegments([]));
  }, [deviceId, workspace?.jobs]);

  const tierCounts = useMemo(() => {
    const high = segments.filter((s) => tierOf(s) === "high").length;
    const medium = segments.filter((s) => tierOf(s) === "medium").length;
    const low = segments.length - high - medium;
    return { high, medium, low };
  }, [segments]);

  async function handleRecover() {
    if (!deviceId || !actor.trim()) {
      toast.error("Select device and enter examiner");
      return;
    }
    setBusy(true);
    setLog([]);
    setWorking("Recovery running…");

    try {
      const started = await api.recover(caseId, deviceId, actor.trim());
      await new Promise<void>((resolve, reject) => {
        subscribeJobEvents(started.job.id, {
          onEvent: (event) => {
            if (event.message) setLog((prev) => [...prev.slice(-200), event.message!]);
            if (event.status === "completed") resolve();
            if (event.status === "failed" || event.status === "cancelled" || event.status === "interrupted") {
              reject(new Error(event.error || event.message || `Recovery ${event.status}`));
            }
          },
          onError: reject,
        });
      });
      const result = await api.getJob(started.job.id);
      setSegments(result.segments);
      toast.success(`${result.segments.length} sequences recovered`);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Recovery failed", { duration: Infinity });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  const adapterHint = workspace?.evidence.find((e) => e.id === deviceId)?.identification?.recommended_adapter;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section className="visily-card flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-[180px] flex-1">
          <label className="label">Evidence image</label>
          <select className="field w-full" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
            {(workspace?.evidence ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.filename}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-[160px]">
          <label className="label">Examiner</label>
          <Input value={actor} onChange={(e) => setActor(e.target.value)} />
        </div>
        <Button disabled={busy || !deviceId} onClick={() => void handleRecover()}>
          Run recovery
        </Button>
        {adapterHint ? (
          <p className="w-full text-[12px] text-[var(--text-secondary)]">
            Recommended adapter from identification: <span className="mono font-medium">{adapterHint}</span>
          </p>
        ) : null}
      </section>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_200px]">
        <section className="visily-card flex min-h-[240px] flex-col overflow-hidden">
          <div className="visily-card-header">
            <span className="visily-card-title">Engine log</span>
          </div>
          <pre className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed text-[var(--text-secondary)]">
            {log.length === 0 ? "Log output appears when a recovery job runs." : log.join("\n")}
          </pre>
        </section>
        <section className="visily-card p-4">
          <p className="visily-card-title mb-3">Confidence tiers</p>
          <dl className="space-y-2 text-[13px]">
            <div className="flex justify-between">
              <dt className="text-[var(--text-secondary)]">High</dt>
              <dd className="mono font-semibold">{tierCounts.high}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--text-secondary)]">Medium</dt>
              <dd className="mono font-semibold">{tierCounts.medium}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--text-secondary)]">Low</dt>
              <dd className="mono font-semibold">{tierCounts.low}</dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="visily-card overflow-hidden">
        <div className="visily-card-header">
          <span className="visily-card-title">Recovered segments</span>
          <span className="mono text-[11px]">{segments.length}</span>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {segments.length === 0 ? (
            <p className="p-4 text-[13px] text-[var(--text-tertiary)]">No segments for this device yet.</p>
          ) : (
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>Ch</th>
                  <th>Byte range</th>
                  <th>Size</th>
                  <th>Timestamp</th>
                  <th>Parser</th>
                  <th>Validation</th>
                </tr>
              </thead>
              <tbody>
                {segments.map((seg) => (
                  <tr key={seg.id}>
                    <td>{seg.channel ?? "—"}</td>
                    <td className="mono">
                      {seg.offset_start != null && seg.offset_end != null
                        ? `${seg.offset_start}–${seg.offset_end}`
                        : seg.offset_time_label ?? "—"}
                    </td>
                    <td className="mono">{formatBytes(seg.byte_length ?? (seg.offset_end ?? 0) - (seg.offset_start ?? 0))}</td>
                    <td className="text-[11px]">
                      <div>{seg.corrected_start_ts ?? seg.recorder_start_ts ?? "—"}</div>
                      <div className="text-[var(--text-tertiary)]">{formatTimestampSource(seg.timestamp_source)}</div>
                    </td>
                    <td className="mono text-[10px]">{seg.parser_name ?? "—"}</td>
                    <td>
                      <ConfidenceBadge tier={tierOf(seg)} label={seg.validation?.replace(/_/g, " ")} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
