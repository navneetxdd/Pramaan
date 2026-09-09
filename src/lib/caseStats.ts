import type { RecoveryJob } from "@/lib/api";

export type SegmentKind = "recording" | "carve" | "filesystem_undelete";

export type SegmentKindCounts = Record<SegmentKind, number>;

type JobStats = {
  segmentsFound?: number;
  segmentsSkippedOutOfBounds?: number;
  segmentsByKind?: SegmentKindCounts;
  progress?: number;
  message?: string;
};

const SEGMENT_KINDS: SegmentKind[] = [
  "recording",
  "carve",
  "filesystem_undelete",
];

function readKindCounts(raw: unknown): SegmentKindCounts | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const source = raw as Record<string, unknown>;
  const counts: SegmentKindCounts = {
    recording: 0,
    carve: 0,
    filesystem_undelete: 0,
  };
  let sawOne = false;
  for (const kind of SEGMENT_KINDS) {
    const value = source[kind];
    if (typeof value === "number") {
      counts[kind] = value;
      sawOne = true;
    }
  }
  return sawOne ? counts : undefined;
}

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
      segmentsSkippedOutOfBounds:
        typeof parsed.segments_skipped_out_of_bounds === "number"
          ? parsed.segments_skipped_out_of_bounds
          : undefined,
      segmentsByKind: readKindCounts(parsed.segments_by_kind),
      progress:
        typeof parsed.progress === "number" ? parsed.progress : undefined,
      message: typeof parsed.message === "string" ? parsed.message : undefined,
    };
  } catch {
    return {};
  }
}

function getLatestRecoveryJobs(jobs: RecoveryJob[]): RecoveryJob[] {
  const latestByDevice = new Map<string, RecoveryJob>();
  for (const job of jobs) {
    if (job.kind && job.kind !== "recovery") continue;
    if (job.status !== "completed") continue;

    const existing = latestByDevice.get(job.image_id);
    if (!existing || (job.started_at ?? "") > (existing.started_at ?? "")) {
      latestByDevice.set(job.image_id, job);
    }
  }
  return Array.from(latestByDevice.values());
}

export function totalRecoveredSegments(jobs: RecoveryJob[]): number {
  return getLatestRecoveryJobs(jobs).reduce(
    (sum, job) => sum + (parseJobStats(job.stats_json).segmentsFound ?? 0),
    0,
  );
}

/**
 * Per-kind recovered-artifact counts merged across every recovery job, or null
 * when no job reported a kind breakdown (older jobs). Callers must not present a
 * single summed total as a recording count; recordings, carves and filesystem
 * undelete are different findings.
 */
export function recoveredSegmentsByKind(
  jobs: RecoveryJob[],
): SegmentKindCounts | null {
  let seen = false;
  const total: SegmentKindCounts = {
    recording: 0,
    carve: 0,
    filesystem_undelete: 0,
  };
  for (const job of getLatestRecoveryJobs(jobs)) {
    const counts = parseJobStats(job.stats_json).segmentsByKind;
    if (!counts) continue;
    seen = true;
    total.recording += counts.recording;
    total.carve += counts.carve;
    total.filesystem_undelete += counts.filesystem_undelete;
  }
  return seen ? total : null;
}

/**
 * Per-kind counts over a segment list (the Recovery table's own rows), using
 * each row's engine-assigned artifact_kind. A row with no kind is counted as a
 * carve, never a recording, so an un-upgraded response cannot inflate the
 * recording tally.
 */
export function countSegmentKinds(
  segments: Array<{ artifact_kind?: string | null }>,
): SegmentKindCounts {
  const counts: SegmentKindCounts = {
    recording: 0,
    carve: 0,
    filesystem_undelete: 0,
  };
  for (const seg of segments) {
    const kind = seg.artifact_kind;
    if (
      kind === "recording" ||
      kind === "carve" ||
      kind === "filesystem_undelete"
    ) {
      counts[kind] += 1;
    } else {
      counts.carve += 1;
    }
  }
  return counts;
}

const SEGMENT_KIND_NOUNS: Record<SegmentKind, [string, string]> = {
  recording: ["recording", "recordings"],
  carve: ["carve", "carves"],
  filesystem_undelete: ["filesystem undelete", "filesystem undelete"],
};

/** "8 recordings · 3 carves · 1 filesystem undelete" — omits zero kinds. */
export function summariseSegmentKinds(counts: SegmentKindCounts): string {
  const parts = SEGMENT_KINDS.filter((kind) => counts[kind] > 0).map((kind) => {
    const [one, many] = SEGMENT_KIND_NOUNS[kind];
    return `${counts[kind]} ${counts[kind] === 1 ? one : many}`;
  });
  return parts.join(" · ");
}

const JOB_KIND_LABELS: Record<string, string> = {
  recovery: "Recovery",
  ai_analytics: "Findings analytics",
  cross_camera: "Cross-camera trace",
  acquisition: "Acquisition",
  physical_imaging: "Physical imaging",
  dataset_fetch: "Validation dataset fetch",
  tool_verification: "Parser verification",
  export: "Segment export",
};

/** Human label for a job kind. The Overview activity list shows every kind, not
 * just recovery, so the examiner sees analytics, export and imaging work too. */
export function jobKindLabel(kind?: string | null): string {
  if (!kind) return "Job";
  return JOB_KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export function failedJobCount(jobs: RecoveryJob[]): number {
  return jobs.filter((j) => j.status === "failed" || j.status === "error")
    .length;
}

export function runningJobs(jobs: RecoveryJob[]): RecoveryJob[] {
  return jobs.filter((j) => j.status === "running" || j.status === "pending");
}

export function jobDisplayProgress(
  job: RecoveryJob,
  liveProgress?: number,
): number | undefined {
  if (job.status === "completed") return 100;
  if (typeof liveProgress === "number") return liveProgress;
  const fromStats = parseJobStats(job.stats_json).progress;
  if (typeof fromStats === "number") return fromStats;
  if (job.status === "running") return undefined;
  return undefined;
}
