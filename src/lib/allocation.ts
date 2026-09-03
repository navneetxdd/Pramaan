import type { Segment } from "@/lib/api";

/**
 * Allocation state of a recovered segment.
 *
 * The Hikvision engine emits `allocation_state` inside `validation_evidence`
 * (see docs/reference/hikvision_fs.md section 7). Other vendors do not yet emit
 * it, so we fall back to their validation vocabulary. Anything we cannot place
 * is reported as `unknown` rather than guessed as allocated — a wrong
 * "allocated" would understate what was recovered.
 */
export type AllocationState = "allocated" | "deleted" | "recording" | "unknown";

/** Validation levels that mean "deleted" for vendors without allocation_state. */
const DELETED_VALIDATIONS = new Set([
  "hikbtree_deleted_entry",
  "honeywell_expired_index",
  "filesystem_deleted_inode",
  "slack_recovered",
  "unreferenced_carve",
  "h264_nal_tail",
]);

const ALLOCATED_VALIDATIONS = new Set([
  "hikbtree_indexed",
  "dual_signature_4",
  "dual_signature",
  "honeywell_index_4",
  "honeywell_format_carve_4",
  "hkvi_block_4",
  "hkvi_block",
]);

export function allocationOf(segment: Segment): AllocationState {
  const raw = segment.validation_evidence?.["allocation_state"];
  if (typeof raw === "string") {
    const value = raw.toLowerCase();
    if (value.startsWith("deleted")) return "deleted";
    if (value.startsWith("recording")) return "recording";
    if (value.startsWith("allocated")) return "allocated";
  }

  const validation = segment.validation ?? "";
  if (DELETED_VALIDATIONS.has(validation)) return "deleted";
  if (ALLOCATED_VALIDATIONS.has(validation)) return "allocated";
  return "unknown";
}

export function allocationLabel(state: AllocationState): string {
  switch (state) {
    case "deleted":
      return "Deleted";
    case "recording":
      return "Recording";
    case "allocated":
      return "Allocated";
    default:
      return "Unknown";
  }
}

/**
 * Longer explanation for the row tooltip. Prefers the engine's own wording —
 * for Hikvision that is the full "deleted (index entry cleared)" phrasing plus
 * the timestamp-confidence basis, so the examiner reads why, not just what.
 */
export function allocationDetail(segment: Segment): string {
  const raw = segment.validation_evidence?.["allocation_state"];
  const basis = segment.validation_evidence?.["timestamp_confidence_basis"];
  const parts: string[] = [];
  if (typeof raw === "string") parts.push(raw);
  if (typeof basis === "string" && basis) parts.push(basis);
  if (parts.length === 0 && segment.validation) parts.push(segment.validation);
  return parts.join(" — ");
}

export type AllocationCounts = Record<AllocationState, number>;

export function countAllocations(segments: Segment[]): AllocationCounts {
  const counts: AllocationCounts = {
    allocated: 0,
    deleted: 0,
    recording: 0,
    unknown: 0,
  };
  for (const segment of segments) counts[allocationOf(segment)] += 1;
  return counts;
}

/** "6 recordings · 1 deleted" — the Recovery header summary. */
export function summariseAllocations(
  total: number,
  counts: AllocationCounts,
): string {
  const noun = total === 1 ? "recording" : "recordings";
  const extras: string[] = [];
  if (counts.deleted > 0) extras.push(`${counts.deleted} deleted`);
  if (counts.recording > 0) extras.push(`${counts.recording} in progress`);
  if (counts.unknown > 0) extras.push(`${counts.unknown} unclassified`);
  return [`${total} ${noun}`, ...extras].join(" · ");
}
