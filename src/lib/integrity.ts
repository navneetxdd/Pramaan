export type IntegrityState =
  | "acquired"
  | "hash_pending"
  | "verified"
  | "mismatch"
  | "interrupted"
  | "missing"
  | "unknown";

export function resolveIntegrityState(
  acquisitionStatus?: string | null,
  verificationStatus?: string | null,
): IntegrityState {
  const acquisition = (acquisitionStatus ?? "complete").toLowerCase();
  const verification = (verificationStatus ?? "pending").toLowerCase();

  if (
    acquisition === "interrupted" ||
    acquisition === "in_progress" ||
    acquisition === "pending"
  ) {
    return "interrupted";
  }
  if (verification === "missing") return "missing";
  if (verification === "mismatch") return "mismatch";
  if (verification === "verified") return "verified";
  if (verification === "pending" || !verification) return "hash_pending";
  if (acquisition === "complete") return "acquired";
  return "unknown";
}

export function integrityLabel(state: IntegrityState): string {
  switch (state) {
    case "verified":
      return "Hash verified";
    case "hash_pending":
      return "Hash pending";
    case "mismatch":
      return "Hash mismatch";
    case "interrupted":
      return "Acquisition interrupted";
    case "missing":
      return "File missing";
    case "acquired":
      return "Acquired";
    default:
      return "Unknown";
  }
}

/** Capability tiers that represent a vendor-specific parser match (Dahua DHAV,
 * Hikvision HIKBTREE, Honeywell). A generic MBR/FAT/NTFS/ext signature routed to
 * generic_tier2 carries capability_tier "filesystem_recovery" or
 * "acquisition_generic_only". Those mean filesystem undelete or generic carving,
 * not vendor identification, and must never be counted as one. Mirrors
 * VENDOR_PARSER_TIERS in engine/app/parsers/manufacturer_detect.py. */
export const VENDOR_PARSER_TIERS = new Set([
  "validated_parser",
  "experimental_parser",
]);

/** Validation scopes that mean "the family byte signature matched, but no
 * validated parser ran for it" (CP Plus, Uniview). A hit like that is a routing
 * hint, not a vendor identification, so it must not count toward the Overview
 * "Vendor identified" tally the way filesystem_recovery once did. */
const SIGNATURE_ONLY_SCOPES = new Set(["signature_match_only"]);

export function isVendorParserHit(hit: {
  capability_tier?: string | null;
  validation_scope?: string | null;
}): boolean {
  if (
    hit.capability_tier == null ||
    !VENDOR_PARSER_TIERS.has(hit.capability_tier)
  ) {
    return false;
  }
  if (
    hit.validation_scope != null &&
    SIGNATURE_ONLY_SCOPES.has(hit.validation_scope)
  ) {
    return false;
  }
  return true;
}

export function capabilityTierLabel(tier: string): string {
  switch (tier) {
    case "validated_parser":
      return "Validated parser (fixture scope)";
    case "experimental_parser":
      return "Experimental parser";
    case "acquisition_generic_only":
      return "Acquisition + generic only";
    default:
      return tier.replace(/_/g, " ");
  }
}

const RECOVERY_ADAPTER_LABELS: Record<string, string> = {
  hikvision: "Hikvision HIKBTREE index",
  dahua_dhav: "Dahua DHAV frame carve",
  honeywell: "Honeywell index",
  h264_carve: "H.264 stream carve",
  generic_tier2: "Generic filesystem / carve",
  needs_selection: "Adapter not selected",
};

/** Recovery adapters are internal engine keys. Examiners see the method name,
 * not the key. The Dahua adapter is a frame carver, never an index parser. */
export function recoveryAdapterLabel(adapter?: string | null): string {
  if (!adapter) return "Adapter not selected";
  return RECOVERY_ADAPTER_LABELS[adapter] ?? adapter.replace(/_/g, " ");
}

export function validationScopeLabel(scope: string): string {
  switch (scope) {
    case "builder_and_known_fixtures":
      return "Proven on builder and known fixtures only";
    case "builder_fixture_only":
      return "Proven on builder fixtures only";
    case "signature_match_only":
      return "Signature match only. Parser not run for this family.";
    case "generic_signature_carving_only":
      return "Generic carving only. No vendor-specific parser.";
    case "annex_b_signature_only":
      return "Generic H.264 signature only. No vendor structure.";
    default:
      return scope.replace(/_/g, " ");
  }
}

const CUSTODY_ACTION_LABELS: Record<string, string> = {
  case_created: "Case created",
  case_exported: "Case exported",
  case_imported: "Case imported",
  evidence_acquired: "Evidence acquired",
  evidence_acquisition_verification_failed: "Evidence verification failed",
  ai_analytics_completed: "AI analytics completed",
  ai_analytics_completed_with_warnings:
    "AI analytics completed (with warnings)",
  ai_analytics_skipped_unavailable: "AI analytics skipped (unavailable)",
  cross_camera_correlation_run: "Cross-camera correlation run",
  cross_camera_still_saved: "Cross-camera still saved as evidence",
  recovery_started: "Recovery started",
  recovery_adapter_manually_selected: "Recovery adapter selected manually",
  recovery_superseded_prior_results: "Recovery re-run, replacing prior results",
  sequence_artifact_created: "Recovered segment added",
  recovery_completed: "Recovery completed",
  recovery_failed: "Recovery failed",
  signed_report_generated: "Signed report generated",
};

/** Custody/audit log actions are internal event codes, some with a ":detail"
 * suffix (e.g. "recovery_adapter_manually_selected:dahua_dhav"). Examiners and
 * the court read this log directly, so show the human label, not the raw code. */
export function custodyActionLabel(action: string): string {
  const [code, detail] = action.split(":", 2);
  const label = CUSTODY_ACTION_LABELS[code] ?? code.replace(/_/g, " ");
  return detail ? `${label}: ${detail}` : label;
}

export function formatTimestampSource(source?: string | null): string {
  if (!source) return "Unavailable";
  return source.replace(/_/g, " ");
}
