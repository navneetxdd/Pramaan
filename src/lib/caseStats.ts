import type { RecoveryJob } from "@/lib/api";

type JobStats = {
  segmentsFound?: number;
  progress?: number;
  message?: string;
};

export function parseJobStats(statsJson: string | null | undefined): JobStats {
  if (!statsJson) return {};
  try {
    const parsed = JSON.parse(statsJson) as Record<string, unknown>;
    return {
      segmentsFound:
        typeof parsed.segments_found === "number"
          ? parsed.segments_found
          : typeof parsed.segmentsFound === "number"
            ? parsed.segmentsFound
            : undefined,
      progress: typeof parsed.progress === "number" ? parsed.progress : undefined,
      message: typeof parsed.message === "string" ? parsed.message : undefined,
    };
  } catch {
    return {};
  }
}

export function totalRecoveredSegments(jobs: RecoveryJob[]): number {
  return jobs.reduce((sum, job) => sum + (parseJobStats(job.stats_json).segmentsFound ?? 0), 0);
}

export function failedJobCount(jobs: RecoveryJob[]): number {
  return jobs.filter((j) => j.status === "failed" || j.status === "error").length;
}

export function runningJobs(jobs: RecoveryJob[]): RecoveryJob[] {
  return jobs.filter((j) => j.status === "running" || j.status === "pending");
}

export function jobDisplayProgress(job: RecoveryJob, liveProgress?: number): number | undefined {
  if (job.status === "completed") return 100;
  if (typeof liveProgress === "number") return liveProgress;
  const fromStats = parseJobStats(job.stats_json).progress;
  if (typeof fromStats === "number") return fromStats;
  if (job.status === "running") return undefined;
  return undefined;
}
