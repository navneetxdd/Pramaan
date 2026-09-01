import { useEffect, useState } from "react";
import { Play, ScanEye, AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type AiFinding } from "@/lib/api";
import { subscribeJobEvents } from "@/lib/sse";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useActivity } from "@/context/ActivityContext";
import { DashboardStat } from "@/components/visily/DashboardStat";

export function CaseAiAnalyticsPage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [actor, setActor] = useState(workspace?.case.examiner_name ?? "");
  const [deviceId, setDeviceId] = useState("");
  const [findings, setFindings] = useState<AiFinding[]>([]);
  const [busy, setBusy] = useState(false);
  const { setWorking, setIdle } = useActivity();

  const devices = workspace?.evidence ?? [];

  useEffect(() => {
    if (devices[0] && !deviceId) setDeviceId(devices[0].id);
  }, [devices, deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    void api.listAiFindings(deviceId).then((r) => setFindings(r.findings)).catch(() => setFindings([]));
  }, [deviceId]);

  async function handleRun() {
    if (!actor.trim() || !deviceId) {
      toast.error("Examiner and device required");
      return;
    }
    setBusy(true);
    setWorking("Running frame sampling…");
    try {
      const started = await api.runAiAnalytics(deviceId, actor.trim());
      await new Promise<void>((resolve, reject) => {
        const unsubscribe = subscribeJobEvents(started.job.id, {
          onEvent: (event) => {
            if (event.status === "completed") {
              unsubscribe();
              resolve();
            }
            if (event.status === "failed") {
              unsubscribe();
              reject(new Error(event.error ?? "Analytics failed"));
            }
          },
          onError: reject,
        });
      });
      const result = await api.listAiFindings(deviceId);
      setFindings(result.findings);
      toast.success(`Analysis complete — ${result.count} lead(s)`);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Analytics failed", { duration: Infinity });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  const motionCount = findings.filter((f) => f.finding_type === "motion").length;
  const sceneCount = findings.filter((f) => f.finding_type === "scene_change").length;
  const faceCount = findings.filter((f) => f.finding_type === "face").length;
  const objectCount = findings.filter((f) => f.finding_type === "object").length;

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1]">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Investigative leads</p>
          <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Findings</h1>
          <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
            Four distinct pipelines: foreground motion, scene change, face candidate, and YOLOX object candidate — leads only.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <DashboardStat label="Total findings" value={String(findings.length)} icon={ScanEye} />
        <DashboardStat label="Motion" value={String(motionCount)} icon={ScanEye} tone="info" />
        <DashboardStat label="Scene change" value={String(sceneCount)} icon={ScanEye} />
        <DashboardStat label="Face" value={String(faceCount)} icon={ScanEye} />
        <DashboardStat label="Object" value={String(objectCount)} icon={AlertTriangle} tone={objectCount > 0 ? "info" : undefined} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
        <section className="visily-card space-y-3 p-3">
          <p className="visily-card-title text-[11px]">Run analysis</p>
          <div className="rounded border border-amber-500/40 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            Investigative leads only — not verified evidence.
          </div>
          {devices.length === 0 ? (
            <p className="text-[12px] text-[var(--text-secondary)]">
              <Link to={`/cases/${caseId}/acquire`} className="text-[var(--accent-500)] underline">
                Acquire evidence
              </Link>{" "}
              and complete recovery before running findings analysis.
            </p>
          ) : (
            <>
              <label className="block text-[12px] text-[var(--text-secondary)]">Examiner</label>
              <Input value={actor} onChange={(e) => setActor(e.target.value)} />
              <label className="block text-[12px] text-[var(--text-secondary)]">Device</label>
              <select className="field w-full" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
                <option value="">Select device</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
              <Button className="w-full" disabled={busy || !deviceId} onClick={() => void handleRun()}>
                <Play className="h-4 w-4" />
                Run 1 fps sampling
              </Button>
            </>
          )}
        </section>

        <section className="visily-card overflow-hidden">
          <div className="visily-card-header">
            <span className="visily-card-title flex items-center gap-2">
              <ScanEye className="h-4 w-4" />
              Findings ({findings.length})
            </span>
          </div>
          {findings.length === 0 ? (
            <p className="p-4 text-[13px] text-[var(--text-tertiary)]">
              No findings yet. Complete recovery, then run analysis to populate timeline markers.
            </p>
          ) : (
            <table className="data-table w-full">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Offset</th>
                  <th>Label</th>
                  <th>Conf.</th>
                  <th>Detector</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.id}>
                    <td className="uppercase">{f.finding_type.replace(/_/g, " ")}</td>
                    <td className="mono">{f.frame_offset_ms}ms</td>
                    <td>{f.label ?? "—"}</td>
                    <td className="mono">{f.confidence != null ? f.confidence.toFixed(2) : "—"}</td>
                    <td className="mono text-[10px]">{f.bbox?.detector ?? f.bbox?.model ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
