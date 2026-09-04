import type { Segment } from "@/lib/api";

/**
 * Parser evidence, rendered honestly.
 *
 * Every parser records what it actually verified in `signature_evidence`. This
 * module summarises that object as-is. It never scores, weights, or averages —
 * a percentage here would be an invention, and inventions are exactly what this
 * panel replaced.
 *
 * The reader is deliberately vendor-agnostic: it walks whatever keys a parser
 * emitted rather than hardcoding Hikvision's, so Dahua/Honeywell/generic
 * segments render without anyone editing this file.
 */

export type CheckKind = "boolean" | "value";

export type CheckSummary = {
  key: string;
  label: string;
  kind: CheckKind;
  /** Segments where the check passed (true, or a non-empty value). */
  passed: number;
  /** Segments whose parser reported this key at all. */
  total: number;
  /** Distinct values observed, for `value` checks (e.g. firmware strings). */
  values: string[];
};

/** Human wording for keys we know. Unknown keys fall back to the key itself. */
const LABELS: Record<string, string> = {
  hikbtree_index: "HIKBTREE index parsed",
  sps_decoded: "H.264 SPS decoded",
  idr_table_read: "IDR table read",
  master_block_signature: "Master sector signature",
  master_block_offset: "HIKBTREE offset",
  system_init_time: "Recorder init time",
  firmware: "Firmware string",
  index_entry: "Index entry matched",
  expired_index_entry: "Expired index entry",
  indexed_length: "Length from index",
  honeywell_layout: "Honeywell layout matched",
  header: "Header signature",
  footer: "Footer signature",
  frame_signatures: "Frame signatures",
  annex_b_start_code: "Annex-B start code",
  nal_marker: "NAL marker",
  bounded_frame_length: "Frame length bounded",
  bounded_frames: "Frames bounded",
  bounded_gop: "GOP bounded",
  validated_length: "Length validated",
  gap_bytes: "Gap bytes",
  tail_bounded_by_scan_end: "Tail bounded by scan end",
};

/** Keys that are bookkeeping, not verification claims. */
const IGNORED = new Set(["recovery_context"]);

/**
 * Keys whose truth means a real on-disk structure was parsed, as opposed to a
 * brand string merely being spotted. Drives the `strong` strength word.
 */
const STRUCTURAL = /index|btree|layout|filesystem|dhfs|footer|header/i;

export function checkLabel(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, " ");
}

function isPassing(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "number") return true;
  return Boolean(value);
}

export function collectChecks(segments: Segment[]): CheckSummary[] {
  const acc = new Map<string, CheckSummary>();

  for (const segment of segments) {
    const evidence = segment.signature_evidence ?? {};
    for (const [key, value] of Object.entries(evidence)) {
      if (IGNORED.has(key)) continue;
      if (value === null || value === undefined) continue;

      let entry = acc.get(key);
      if (!entry) {
        entry = {
          key,
          label: checkLabel(key),
          kind: typeof value === "boolean" ? "boolean" : "value",
          passed: 0,
          total: 0,
          values: [],
        };
        acc.set(key, entry);
      }
      entry.total += 1;
      if (isPassing(value)) entry.passed += 1;
      if (entry.kind === "value") {
        const text = String(value);
        if (text && !entry.values.includes(text)) entry.values.push(text);
      }
    }
  }

  // Booleans first (they are the real pass/fail claims), then values; each
  // group ordered by how many segments the parser reported it for.
  return [...acc.values()].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "boolean" ? -1 : 1;
    return b.total - a.total || a.label.localeCompare(b.label);
  });
}

export type Strength = "strong" | "weak" | "none";

/**
 * Strength of the evidence behind one segment.
 *
 *  strong — a filesystem/index structure was parsed for this segment
 *  weak   — only signature or brand evidence was found, no structure parsed
 *  none   — the parser recorded no usable evidence
 *
 * This is a statement about which checks passed, not a score.
 */
export function strengthOf(segment: Segment): Strength {
  const evidence = segment.signature_evidence ?? {};
  const entries = Object.entries(evidence).filter(
    ([key, value]) =>
      !IGNORED.has(key) && value !== null && value !== undefined,
  );
  if (entries.length === 0) return "none";

  const structural = entries.some(
    ([key, value]) => STRUCTURAL.test(key) && isPassing(value),
  );
  if (structural) return "strong";

  return entries.some(([, value]) => isPassing(value)) ? "weak" : "none";
}

export function strengthCounts(segments: Segment[]): Record<Strength, number> {
  const counts: Record<Strength, number> = { strong: 0, weak: 0, none: 0 };
  for (const segment of segments) counts[strengthOf(segment)] += 1;
  return counts;
}

export function strengthColor(strength: Strength): string {
  switch (strength) {
    case "strong":
      return "var(--status-success)";
    case "weak":
      return "var(--status-warning)";
    default:
      return "var(--text-tertiary)";
  }
}

/**
 * Colour tier for a *real* timestamp confidence.
 *
 * Thresholds mirror the engine's documented ladder
 * (docs/reference/hikvision_fs.md section 7.1): 0.9 index-derived,
 * 0.5 residual after a cleared index entry, 0.3 recovered from the IDR table.
 * The number shown to the examiner is always the engine's own — this only
 * chooses a colour for it.
 */
export function timestampTier(confidence?: number | null): string {
  if (confidence == null) return "low";
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.45) return "medium";
  return "low";
}
