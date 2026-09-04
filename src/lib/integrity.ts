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

export function validationScopeLabel(scope: string): string {
  switch (scope) {
    case "synthetic_and_known_fixtures":
      return "Proven on synthetic + known fixtures only";
    case "synthetic_fixture_only":
      return "Proven on synthetic fixtures only";
    case "signature_match_only":
      return "Signature match only — parser not run for this family";
    case "generic_signature_carving_only":
      return "Generic carving only — no vendor-specific parser";
    case "annex_b_signature_only":
      return "Generic H.264 signature only — no vendor structure";
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
  ai_analytics_skipped_unavailable: "AI analytics skipped — unavailable",
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
 * judges read this log directly — show the human label, not the raw code. */
export function custodyActionLabel(action: string): string {
  const [code, detail] = action.split(":", 2);
  const label = CUSTODY_ACTION_LABELS[code] ?? code.replace(/_/g, " ");
  return detail ? `${label}: ${detail}` : label;
}

export function formatTimestampSource(source?: string | null): string {
  if (!source) return "Unavailable";
  return source.replace(/_/g, " ");
}
