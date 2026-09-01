import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type Segment } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfidenceBadge } from "@/components/forensic/ConfidenceBadge";
import { ConfidenceDonut, RecoveryLogPanel } from "@/components/forensic/ConfidenceDonut";
import { VirtualTable } from "@/components/ui/virtual-table";
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
  const logRef = useRef<HTMLDivElement>(null);
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

  const recoveryRunning = useMemo(
    () =>
      workspace?.jobs.some(
        (job) =>
          job.kind === "recovery" &&
          (job.device_id === deviceId || job.image_id === deviceId) &&
          (job.status === "running" || job.status === "pending"),
      ) ?? false,
    [workspace?.jobs, deviceId],
  );

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [log]);

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
        <Button disabled={busy || !deviceId || recoveryRunning} onClick={() => void handleRecover()}>
          {recoveryRunning ? "Recovery in progress…" : "Run recovery"}
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
          <div ref={logRef} className="flex min-h-[240px] flex-1 flex-col overflow-hidden">
            <RecoveryLogPanel lines={log} />
          </div>
        </section>
        <section className="visily-card p-4">
          <p className="visily-card-title mb-3">Confidence tiers</p>
          <ConfidenceDonut high={tierCounts.high} medium={tierCounts.medium} low={tierCounts.low} />
        </section>
      </div>

      <section className="visily-card overflow-hidden">
        <div className="visily-card-header">
          <span className="visily-card-title">Recovered segments</span>
          <span className="mono text-[11px]">{segments.length}</span>
        </div>
        <VirtualTable
          rows={segments}
          maxHeight={288}
          emptyMessage="No segments for this device yet."
          columns={[
            { key: "ch", header: "Ch", cell: (seg) => seg.channel ?? "—" },
            {
              key: "range",
              header: "Byte range",
              className: "mono",
              cell: (seg) =>
                seg.offset_start != null && seg.offset_end != null
                  ? `${seg.offset_start}–${seg.offset_end}`
                  : seg.offset_time_label ?? "—",
            },
            {
              key: "size",
              header: "Size",
              className: "mono",
              cell: (seg) => formatBytes(seg.byte_length ?? (seg.offset_end ?? 0) - (seg.offset_start ?? 0)),
            },
            {
              key: "ts",
              header: "Timestamp",
              cell: (seg) => (
                <div className="text-[11px]">
                  <div>{seg.corrected_start_ts ?? seg.recorder_start_ts ?? "—"}</div>
                  <div className="text-[var(--text-tertiary)]">{formatTimestampSource(seg.timestamp_source)}</div>
                </div>
              ),
            },
            { key: "parser", header: "Parser", className: "mono text-[10px]", cell: (seg) => seg.parser_name ?? "—" },
            {
              key: "validation",
              header: "Validation",
              cell: (seg) => <ConfidenceBadge tier={tierOf(seg)} label={seg.validation?.replace(/_/g, " ")} />,
            },
          ]}
        />
      </section>
    </div>
  );
}
