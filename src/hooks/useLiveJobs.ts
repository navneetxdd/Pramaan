import { useEffect, useState } from "react";
import type { RecoveryJob } from "@/lib/api";
import { api } from "@/lib/api";

export type LiveJobState = {
  progress: number;
  message: string;
  status: string;
};

export function useLiveJobs(jobs: RecoveryJob[], refreshMs = 2000) {
  const [live, setLive] = useState<Record<string, LiveJobState>>({});

  useEffect(() => {
    const active = jobs.filter((j) => j.status === "running" || j.status === "pending");
    if (active.length === 0) {
      setLive({});
      return;
    }

    let cancelled = false;
    async function poll() {
      const next: Record<string, LiveJobState> = {};
      await Promise.all(
        active.map(async (job) => {
          try {
            const s = await api.getJobStatus(job.id);
            next[job.id] = {
              progress: typeof s.progress === "number" ? s.progress : 0,
              message: s.message ?? "",
              status: s.status,
            };
          } catch {
            next[job.id] = { progress: 0, message: job.status, status: job.status };
          }
        }),
      );
      if (!cancelled) setLive(next);
    }

    void poll();
    const timer = window.setInterval(poll, refreshMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobs, refreshMs]);

  return live;
}
