import { useEffect, useState } from "react";
import { BadgeCheck, Download, FileText } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { subscribeJobEvents } from "@/lib/sse";
import { useActivity } from "@/context/ActivityContext";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { CheckCircle2, History } from "lucide-react";

type RunResult = {
  id: string;
  run_at: string;
  app_version: string;
  passed: number;
  results: {
    stages: Array<{ stage: string; passed: boolean; detail: string }>;
    passed: boolean;
    app_version: string;
    vendors_verified: string[];
  };
};

export function ToolVerificationPage() {
  const [runs, setRuns] = useState<RunResult[]>([]);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const { setWorking, setIdle } = useActivity();

  async function loadRuns() {
    try {
      const results = await api.listToolVerificationResults();
      setRuns(results);
      return results;
    } catch {
      setRuns([]);
      return [];
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  async function handleRun() {
    setRunning(true);
    setLog([]);
    setWorking("Tool verification running…");
    try {
      const { job_id } = await api.runToolVerification();
      await new Promise<void>((resolve, reject) => {
        subscribeJobEvents(job_id, {
          onEvent: (event) => {
            if (event.message) setLog((p) => [...p, event.message!]);
            if (event.status === "completed") resolve();
            if (event.status === "failed") reject(new Error(event.error || "Verification failed"));
          },
          onError: reject,
        });
      });
      const updatedRuns = await loadRuns();
      if (updatedRuns[0]?.passed) {
        toast.success("Tool verification passed");
      } else {
        toast.error("Verification completed with failed checks", { duration: Infinity });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Verification failed", { duration: Infinity });
    } finally {
      setRunning(false);
      setIdle();
    }
  }

  const latest = runs[0];
  const stages = latest?.results?.stages ?? [];
  const passCount = stages.filter((stage) => stage.passed).length;
  const totalChecks = stages.length;

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Engine validation</p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Tool verification</h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Offline regression suite for hash, adapter, and recovery pipeline claims.
            </p>
          </div>
          <Button disabled={running} onClick={() => void handleRun()}>
            <BadgeCheck className="h-4 w-4" />
            Run verification suite
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <DashboardStat label="Total runs" value={String(runs.length)} icon={History} />
        <DashboardStat
          label="Latest result"
          value={latest ? (latest.passed ? "PASS" : "FAIL") : "—"}
          icon={CheckCircle2}
          tone={latest?.passed ? "success" : latest ? "danger" : undefined}
        />
        <DashboardStat label="Checks passed" value={latest ? `${passCount}/${totalChecks}` : "—"} icon={BadgeCheck} tone="info" />
      </div>

      {running ? (
        <section className="visily-card p-3">
          <p className="visily-card-title mb-2 text-[11px]">Live output</p>
          <pre className="max-h-48 overflow-y-auto font-mono text-[11px] text-[var(--text-secondary)]">
            {log.join("\n") || "Running…"}
          </pre>
        </section>
      ) : null}

      {latest ? (
        <section className="visily-card p-3">
          <div className="visily-card-header px-0 pt-0">
            <span className="visily-card-title">Latest run</span>
            <div className="flex items-center gap-2">
              <a
                href={api.toolVerificationHtmlUrl(latest.id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--accent-500)]"
              >
                <FileText className="h-3.5 w-3.5" />
                HTML
              </a>
              <a
                href={api.toolVerificationPdfUrl(latest.id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--accent-500)]"
              >
                <Download className="h-3.5 w-3.5" />
                Signed PDF
              </a>
              <span className="mono text-[var(--status-success)]">{latest.passed ? "PASS" : "FAIL"}</span>
            </div>
          </div>
          <p className="mono mb-3 text-[12px] text-[var(--text-tertiary)]">
            {latest.run_at} · v{latest.app_version}
          </p>
          <ul className="space-y-1">
            {stages.map((result) => (
              <li
                key={result.stage}
                className="flex items-center justify-between rounded border border-[var(--border-subtle)] px-2 py-1.5 text-[13px]"
              >
                <span>{result.stage}</span>
                <span
                  className="font-mono text-[11px]"
                  style={{ color: result.passed ? "var(--status-success)" : "var(--status-danger)" }}
                >
                  {result.passed ? "pass" : "fail"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-[13px] text-[var(--text-tertiary)]">No verification runs recorded yet.</p>
      )}
    </div>
  );
}
