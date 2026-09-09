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

  const activeIds = jobs
    .filter((j) => j.status === "running" || j.status === "pending")
    .map((j) => j.id)
    .sort()
    .join(",");

  useEffect(() => {
    if (!activeIds) {
      setLive({});
      return;
    }

    const idsToPoll = activeIds.split(",");

    let cancelled = false;
    async function poll() {
      const next: Record<string, LiveJobState> = {};
      await Promise.all(
        idsToPoll.map(async (id) => {
          try {
            const s = await api.getJobStatus(id);
            next[id] = {
              progress: typeof s.progress === "number" ? s.progress : 0,
              message: s.message ?? "",
              status: s.status,
            };
          } catch {
            next[id] = {
              progress: 0,
              message: "error",
              status: "error",
            };
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
  }, [activeIds, refreshMs]);

  return live;
}
