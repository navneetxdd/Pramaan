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

/**
 * Whether the recovered bytes are all there.
 *
 * Independent of {@link AllocationState}: allocation state says what the recorder's
 * index claims, recovery status says what is physically on the platter. A recording
 * can be allocated and partial at once — still indexed, but its data block was partly
 * reused. Missing bytes are reported missing; nothing is reconstructed.
 */
export function isPartial(segment: Segment): boolean {
  const evidence = segment.validation_evidence;
  if (evidence?.["partial"] === true) return true;
  return evidence?.["recovery_status"] === "partial";
}

export function partialReason(segment: Segment): string {
  const reason = segment.validation_evidence?.["partial_reason"];
  return typeof reason === "string" ? reason : "";
}

/**
 * Whether the recorder's index was read all the way to its documented end.
 *
 * The Hikvision engine emits `index_complete` / `index_traversal_status` (see
 * docs/reference/hikvision_fs.md §7.6). "6 recordings" and "6 recordings found
 * before the index broke" are different findings about the same disk, so the
 * inventory must not be presented as whole when it isn't.
 *
 * Vendors that do not report a traversal status return `null` — absence of the
 * field is not evidence of a truncated index, and must never render a warning.
 */
export function indexTruncation(
  segments: Segment[],
): { status: string; detail: string } | null {
  for (const segment of segments) {
    const evidence = segment.validation_evidence;
    if (evidence?.["index_complete"] !== false) continue;
    const status = evidence["index_traversal_status"];
    const detail = evidence["index_traversal_detail"];
    return {
      status: typeof status === "string" ? status : "incomplete",
      detail: typeof detail === "string" ? detail : "",
    };
  }
  return null;
}

/** Human wording for a traversal status — reference doc §7.6. */
export function truncationLabel(status: string): string {
  switch (status) {
    case "loop":
      return "the index loops back on itself";
    case "out_of_bounds":
      return "an index pointer addresses bytes outside the image";
    case "malformed_page":
      return "an index page is truncated by the end of the image";
    case "page_limit":
      return "the index is longer than the engine will follow";
    case "no_index":
      return "the index could not be read at all";
    default:
      return "the index could not be read to its end";
  }
}
