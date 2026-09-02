import { useEffect, useState } from "react";
import { Play, ScanEye, AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type AiFinding } from "@/lib/api";
import { subscribeJobEvents } from "@/lib/sse";
import { Button } from "@/components/ui/button";
import { VirtualTable } from "@/components/ui/virtual-table";
import { Input } from "@/components/ui/input";
import { useActivity } from "@/context/ActivityContext";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { PageHeader } from "@/components/visily/PageHeader";

export function CaseAiAnalyticsPage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [actor, setActor] = useState(workspace?.case.examiner_name ?? "");
  const [deviceId, setDeviceId] = useState("");
  const [findings, setFindings] = useState<AiFinding[]>([]);
  const [busy, setBusy] = useState(false);
  const [demoUnavailable, setDemoUnavailable] = useState<string | null>(null);
  const { setWorking, setIdle } = useActivity();

  const devices = workspace?.evidence ?? [];

  useEffect(() => {
    if (devices[0] && !deviceId) setDeviceId(devices[0].id);
  }, [devices, deviceId]);

  useEffect(() => {
    if (!deviceId) return;
    void api
      .listAiFindings(deviceId)
      .then((r) => setFindings(r.findings))
      .catch(() => setFindings([]));
  }, [deviceId]);

  async function handleRun() {
    if (!actor.trim() || !deviceId) {
      toast.error("Examiner and device required");
      return;
    }
    setBusy(true);
    setDemoUnavailable(null);
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
      const status = await api.getJobStatus(started.job.id);
      const parsed = (status.result ?? {}) as {
        demo_mode_unavailable?: boolean;
        message?: string;
      };
      if (parsed.demo_mode_unavailable) {
        setDemoUnavailable(
          parsed.message ??
            "OpenCV/decodable video unavailable on this host — analytics skipped",
        );
      }
      const resultFindings = await api.listAiFindings(deviceId);
      setFindings(resultFindings.findings);
      toast.success(
        parsed?.demo_mode_unavailable
          ? "Analytics unavailable on this host"
          : `Analysis complete — ${resultFindings.count} lead(s)`,
      );
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Analytics failed", {
        duration: Infinity,
      });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  async function toggleReportState(finding: AiFinding) {
    const next = finding.report_state === "INCLUDED" ? "EXCLUDED" : "INCLUDED";
    try {
      const result = await api.updateAiFindingReportState(finding.id, next);
      setFindings((prev) =>
        prev.map((item) => (item.id === finding.id ? result.finding : item)),
      );
      toast.success(
        next === "INCLUDED"
          ? "Lead included in report"
          : "Lead excluded from report",
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  }

  const motionCount = findings.filter(
    (f) => f.finding_type === "motion",
  ).length;
  const sceneCount = findings.filter(
    (f) => f.finding_type === "scene_change",
  ).length;
  const faceCount = findings.filter((f) => f.finding_type === "face").length;
  const objectCount = findings.filter(
    (f) => f.finding_type === "object",
  ).length;

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        kicker="Investigative leads"
        title="Findings"
        subtitle="Four distinct pipelines: foreground motion, scene change, face candidate, and YOLOX object candidate — leads only."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {demoUnavailable ? (
          <div className="visily-card col-span-full flex items-start gap-3 border border-amber-500/40 bg-amber-50 p-4 text-amber-950">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="text-[13px] font-semibold">
                Analytics unavailable on this host
              </p>
              <p className="mt-1 text-[12px]">{demoUnavailable}</p>
            </div>
          </div>
        ) : null}
        <DashboardStat
          label="Total findings"
          value={String(findings.length)}
          icon={ScanEye}
        />
        <DashboardStat
          label="Motion"
          value={String(motionCount)}
          icon={ScanEye}
          tone="info"
        />
        <DashboardStat
          label="Scene change"
          value={String(sceneCount)}
          icon={ScanEye}
        />
        <DashboardStat label="Face" value={String(faceCount)} icon={ScanEye} />
        <DashboardStat
          label="Object"
          value={String(objectCount)}
          icon={AlertTriangle}
          tone={objectCount > 0 ? "info" : undefined}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
        <section className="visily-card space-y-3 p-3">
          <p className="visily-card-title text-[11px]">Run analysis</p>
          <div className="rounded border border-amber-500/40 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            Investigative leads only — not verified evidence.
          </div>
          {devices.length === 0 ? (
            <p className="text-[12px] text-[var(--text-secondary)]">
              <Link
                to={`/cases/${caseId}/acquire`}
                className="text-[var(--accent-500)] underline"
              >
                Acquire evidence
              </Link>{" "}
              and complete recovery before running findings analysis.
            </p>
          ) : (
            <>
              <label className="block text-[12px] text-[var(--text-secondary)]">
                Examiner
              </label>
              <Input value={actor} onChange={(e) => setActor(e.target.value)} />
              <label className="block text-[12px] text-[var(--text-secondary)]">
                Device
              </label>
              <select
                className="field w-full"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
              >
                <option value="">Select device</option>
                {devices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
              <Button
                className="w-full"
                disabled={busy || !deviceId}
                onClick={() => void handleRun()}
              >
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
          <VirtualTable
            rows={findings}
            maxHeight={420}
            emptyMessage="No findings yet. Complete recovery, then run analysis to populate timeline markers."
            columns={[
              {
                key: "type",
                header: "Type",
                cell: (f) => f.finding_type.replace(/_/g, " "),
              },
              {
                key: "offset",
                header: "Offset",
                className: "mono",
                cell: (f) => `${f.frame_offset_ms}ms`,
              },
              { key: "label", header: "Label", cell: (f) => f.label ?? "—" },
              {
                key: "conf",
                header: "Conf.",
                className: "mono",
                cell: (f) =>
                  f.confidence != null ? f.confidence.toFixed(2) : "—",
              },
              {
                key: "detector",
                header: "Detector",
                className: "mono text-[10px]",
                cell: (f) => f.bbox?.detector ?? f.bbox?.model ?? "—",
              },
              {
                key: "report",
                header: "Report",
                cell: (f) => (
                  <Button
                    size="sm"
                    variant={
                      f.report_state === "INCLUDED" ? "default" : "secondary"
                    }
                    onClick={() => void toggleReportState(f)}
                  >
                    {f.report_state === "INCLUDED" ? "Included" : "Include"}
                  </Button>
                ),
              },
            ]}
          />
        </section>
      </div>
    </div>
  );
}
