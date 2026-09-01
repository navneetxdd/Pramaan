import type { CaseRecord } from "@/lib/api";

/** Names produced by smoke tests, CI, and automated validation — hidden from the operator registry. */
const AUTOMATED_NAME_PATTERNS: RegExp[] = [
  /^M\d[\s_]/i,
  /^Smoke[\s_]/i,
  /^Custody gate$/i,
  /^Tool Verification$/i,
  /^verify_/i,
  /^Public media validation$/i,
  /^CAVIAR analytics$/i,
  /^E01 OEM$/i,
  /^M5 Export$/i,
  /^dbg$/i,
];

export function isAutomatedCase(record: Pick<CaseRecord, "name" | "ephemeral">): boolean {
  if (record.ephemeral) return true;
  return AUTOMATED_NAME_PATTERNS.some((pattern) => pattern.test(record.name.trim()));
}

export function filterOperatorCases<T extends Pick<CaseRecord, "name" | "ephemeral">>(cases: T[]): T[] {
  return cases.filter((item) => !isAutomatedCase(item));
}

export function formatCaseRef(caseId: string): string {
  return `CASE-${caseId.slice(0, 8).toUpperCase()}`;
}

export const HANDLER_FIELD_LABEL = "Your name (recorded on chain of custody)";
export const HANDLER_FIELD_HINT =
  "Who is performing this action — written into the custody log as the actor for each step.";
