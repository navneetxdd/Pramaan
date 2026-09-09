/**
 * Evidence Catalog derivations.
 *
 * Every value here is read from a field the engine actually stores and emits.
 * Nothing is guessed from a filename: an examiner renaming an image must not be
 * able to change how the catalog classifies it, and a classification the
 * backend never made must never appear as if it had.
 *
 * Field sources (engine/app/core/db.py `devices`, mapped by
 * engine/app/services/acquisition.py `_device_as_evidence`):
 *   - acquisition_method  devices.acquisition_method
 *   - media_type          infer_media_type(image_path) — the engine's own class
 *   - verification_status devices.verification_status
 *   - acquisition_status  devices.acquisition_status
 */
import type { CustodyEvent, EvidenceRecord } from "./api";
import {
  integrityLabel,
  resolveIntegrityState,
  type IntegrityState,
} from "./integrity";

/* ------------------------------------------------------------------ */
/* Category                                                            */
/* ------------------------------------------------------------------ */

export type EvidenceCategory = "block" | "disk" | "logical" | "unclassified";

/** acquisition_method values the engine writes. Mirrors:
 *  - "forensic_block_imaging"     engine/app/services/physical_imaging.py
 *  - "block_copy"                 engine/app/core/repository.py
 *                                 `create_pending_device` default — the row a
 *                                 chunked block image is written into before
 *                                 the run completes and the method is restated
 *                                 as forensic_block_imaging
 *  - "logical_file_acquisition"   engine/app/core/repository.py (default)
 *  - "operator_oem_image"         engine/app/services/acquisition.py
 *  - "logical_network"            engine/app/services/logical_acquisition.py
 */
const ACQUISITION_METHOD_CATEGORY: Record<string, EvidenceCategory> = {
  forensic_block_imaging: "block",
  block_copy: "block",
  logical_file_acquisition: "disk",
  operator_oem_image: "disk",
  logical_network: "logical",
};

/** media_type values from engine/app/services/acquisition.py `infer_media_type`. */
const MEDIA_TYPE_CATEGORY: Record<string, EvidenceCategory> = {
  disk_image: "disk",
  ewf_image: "disk",
  video_clip: "logical",
  logical_export: "logical",
};

/**
 * Category from stored fields only. acquisition_method wins because it records
 * how the copy was actually taken; media_type is the fallback for rows acquired
 * before the method column was populated. An unrecognised value is reported as
 * unclassified rather than folded into a bucket it may not belong in.
 */
export function categoryOf(item: EvidenceRecord): EvidenceCategory {
  const method = item.acquisition_method;
  if (method && method in ACQUISITION_METHOD_CATEGORY) {
    const fromMethod = ACQUISITION_METHOD_CATEGORY[method];
    // A block-imaged acquisition is a block image regardless of container.
    if (fromMethod === "block") return "block";
    // Otherwise let the concrete media class refine "logical vs disk".
    return MEDIA_TYPE_CATEGORY[item.media_type] ?? fromMethod;
  }
  return MEDIA_TYPE_CATEGORY[item.media_type] ?? "unclassified";
}

export const EVIDENCE_CATEGORIES: EvidenceCategory[] = [
  "block",
  "disk",
  "logical",
  "unclassified",
];

export function categoryLabel(category: EvidenceCategory): string {
  switch (category) {
    case "block":
      return "Block image";
    case "disk":
      return "Disk image";
    case "logical":
      return "Logical export";
    default:
      return "Unclassified";
  }
}

export function categoryDescription(category: EvidenceCategory): string {
  switch (category) {
    case "block":
      return "Bit-for-bit physical acquisition (acquisition_method = forensic_block_imaging).";
    case "disk":
      return "Whole-image file acquired or imported as a disk/EWF image.";
    case "logical":
      return "Clip or logical export pulled from a live recorder — not a forensic image of the media.";
    default:
      return "The engine stored no acquisition_method or media_type this build recognises. Report it rather than acting on it.";
  }
}

/* ------------------------------------------------------------------ */
/* Media type (replaces the old filename-extension "evidence type")    */
/* ------------------------------------------------------------------ */

export const MEDIA_TYPES = [
  "disk_image",
  "ewf_image",
  "video_clip",
  "logical_export",
] as const;

const MEDIA_TYPE_LABELS: Record<string, string> = {
  disk_image: "Raw disk image",
  ewf_image: "EWF / E01",
  video_clip: "Video clip",
  logical_export: "Logical export",
};

export function mediaTypeLabel(mediaType?: string | null): string {
  if (!mediaType) return "Not recorded";
  return MEDIA_TYPE_LABELS[mediaType] ?? mediaType.replace(/_/g, " ");
}

export function isKnownMediaType(mediaType?: string | null): boolean {
  return Boolean(mediaType && mediaType in MEDIA_TYPE_LABELS);
}

/* ------------------------------------------------------------------ */
/* Verification status — read straight off the record                  */
/* ------------------------------------------------------------------ */

/**
 * The complete set of verification_status values the engine writes:
 *   "pending"                    devices schema default
 *   "verified"                   repository.register_device_from_path,
 *                                physical_imaging when the copy hash matched
 *   "verified_with_read_errors"  physical_imaging, copy matched over bad sectors
 *   "mismatch"                   physical_imaging, destination hash disagreed
 * Anything outside this set is a backend value this UI has never been taught,
 * and is surfaced as such instead of being mapped onto a friendlier word.
 */
export const KNOWN_VERIFICATION_STATUSES = [
  "pending",
  "verified",
  "verified_with_read_errors",
  "mismatch",
] as const;

export type VerificationStatus = (typeof KNOWN_VERIFICATION_STATUSES)[number];

export function verificationStatusOf(item: EvidenceRecord): string {
  return item.verification_status ?? "pending";
}

export function isKnownVerificationStatus(value: string): boolean {
  return (KNOWN_VERIFICATION_STATUSES as readonly string[]).includes(value);
}

export function verificationStatusLabel(value: string): string {
  switch (value) {
    case "verified":
      return "Verified";
    case "verified_with_read_errors":
      return "Verified (read errors)";
    case "pending":
      return "Awaiting hash";
    case "mismatch":
      return "Hash mismatch";
    default:
      return value.replace(/_/g, " ");
  }
}

export type StatusTone = "success" | "warning" | "danger" | "neutral";

export function verificationStatusTone(value: string): StatusTone {
  switch (value) {
    case "verified":
      return "success";
    case "verified_with_read_errors":
      return "warning";
    case "pending":
      return "neutral";
    case "mismatch":
      return "danger";
    // An unrecognised backend value is a defect, not a neutral state.
    default:
      return "danger";
  }
}

/** Acquisition progress, which is a different axis from hash verification. */
export function acquisitionStatusLabel(value?: string | null): string {
  if (!value) return "Not recorded";
  return value.replace(/_/g, " ");
}

export function integrityStateOf(item: EvidenceRecord): IntegrityState {
  return resolveIntegrityState(
    item.acquisition_status,
    item.verification_status,
  );
}

export { integrityLabel };

/* ------------------------------------------------------------------ */
/* Custody binding and hash cross-check                                */
/* ------------------------------------------------------------------ */

const SHA256_DIGEST_PREFIX = "sha256:";

/**
 * Custody rows bound to one evidence item.
 *
 * The custody log is written with target_type='case' for every row
 * (engine/app/core/repository.py), so there is no image_id to filter on. The
 * one real binding is evidence_digest, which acquisition stores as
 * "sha256:<image hash>". Matching on it gives the events that provably concern
 * this image; anything else in the log belongs to the case, not to this item.
 */
export function custodyEventsForItem(
  item: EvidenceRecord,
  events: CustodyEvent[],
): CustodyEvent[] {
  const digest = normaliseDigest(item.sha256);
  if (!digest) return [];
  return events.filter(
    (event) => normaliseDigest(event.evidence_digest) === digest,
  );
}

function normaliseDigest(value?: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim().toLowerCase();
  const bare = trimmed.startsWith(SHA256_DIGEST_PREFIX)
    ? trimmed.slice(SHA256_DIGEST_PREFIX.length)
    : trimmed;
  return /^[0-9a-f]{64}$/.test(bare) ? bare : null;
}

/** Custody action that records an acquisition against the case, written by
 *  `register_device_from_path` in engine/app/core/repository.py with the
 *  acquired image's digest. Actions may carry a ":detail" suffix, hence the
 *  prefix test rather than equality. */
const EVIDENCE_ACQUIRED_ACTION = "evidence_acquired";

function isAcquisitionRow(event: CustodyEvent): boolean {
  return (event.action ?? "").startsWith(EVIDENCE_ACQUIRED_ACTION);
}

export type HashCrossCheck =
  | { state: "match"; custodyDigest: string; eventCount: number }
  | { state: "mismatch"; custodyDigest: string; eventCount: number }
  | { state: "no_custody_digest" }
  | { state: "no_stored_hash" };

/**
 * Compare two values that are already stored — the catalog record's sha256 and
 * the digest the custody log recorded when the item was acquired. Nothing is
 * re-hashed here; this answers "do the two books agree?", which is the check an
 * examiner needs before relying on either.
 *
 * The comparison deliberately does NOT start from `custodyEventsForItem`. That
 * helper binds rows to an item *by* the hash, so a record whose hash had been
 * altered would simply match nothing, and every surviving row would agree with
 * itself — the warning could never fire. Instead this looks at the case's
 * acquisition rows as a set:
 *
 *   - this item's hash is among them            -> match
 *   - it is not, and some acquisition digest is
 *     claimed by no evidence record in the case -> mismatch. Custody recorded
 *     an acquisition whose hash nothing in the
 *     catalog accounts for, while this item
 *     carries no custody hash of its own.
 *   - it is not, and every acquisition digest is
 *     accounted for elsewhere                   -> no_custody_digest. This item
 *     was never logged with a hash; that is a
 *     gap, not a contradiction.
 *
 * `caseEvidence` is the whole case's evidence list, needed only to decide which
 * of those two "no match" readings is true.
 */
export function crossCheckHash(
  item: EvidenceRecord,
  events: CustodyEvent[],
  caseEvidence: EvidenceRecord[],
): HashCrossCheck {
  const recordDigest = normaliseDigest(item.sha256);
  if (!recordDigest) return { state: "no_stored_hash" };

  const acquisitionDigests = events
    .filter(isAcquisitionRow)
    .map((event) => normaliseDigest(event.evidence_digest))
    .filter((value): value is string => value !== null);
  if (acquisitionDigests.length === 0) return { state: "no_custody_digest" };

  const matching = acquisitionDigests.filter((value) => value === recordDigest);
  if (matching.length > 0) {
    return {
      state: "match",
      custodyDigest: recordDigest,
      eventCount: matching.length,
    };
  }

  const claimed = new Set(
    caseEvidence
      .map((record) => normaliseDigest(record.sha256))
      .filter((value): value is string => value !== null),
  );
  const unclaimed = acquisitionDigests.filter((digest) => !claimed.has(digest));
  if (unclaimed.length > 0) {
    return {
      state: "mismatch",
      custodyDigest: unclaimed[0],
      eventCount: unclaimed.length,
    };
  }

  return { state: "no_custody_digest" };
}

export function hashCrossCheckLabel(check: HashCrossCheck): string {
  switch (check.state) {
    case "match":
      return "Verified — hash matches custody log";
    case "mismatch":
      return "Hash disagrees with custody log";
    case "no_custody_digest":
      return "No custody entry records a hash for this item";
    default:
      return "No hash stored on this evidence record";
  }
}
