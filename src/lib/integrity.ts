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

  if (acquisition === "interrupted" || acquisition === "in_progress" || acquisition === "pending") {
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

export function formatTimestampSource(source?: string | null): string {
  if (!source) return "Unavailable";
  return source.replace(/_/g, " ");
}
