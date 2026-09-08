import type { CaseRecord } from "@/lib/api";

/**
 * Cases created by the automated test and CI suites. Those runs mark their
 * cases `ephemeral`, which is the real signal; the name patterns below only
 * catch older automation output on a developer machine and are deliberately
 * narrow so they can never hide a case an examiner actually named.
 */
const AUTOMATED_NAME_PATTERNS: RegExp[] = [
  /^Smoke[\s_]/i,
  /^verify_/i,
  /^dbg$/i,
];

export function isAutomatedCase(
  record: Pick<CaseRecord, "name" | "ephemeral">,
): boolean {
  if (record.ephemeral) return true;
  return AUTOMATED_NAME_PATTERNS.some((pattern) =>
    pattern.test(record.name.trim()),
  );
}

export function filterOperatorCases<
  T extends Pick<CaseRecord, "name" | "ephemeral">,
>(cases: T[]): T[] {
  return cases.filter((item) => !isAutomatedCase(item));
}

export function formatCaseRef(caseId: string): string {
  return `CASE-${caseId.slice(0, 8).toUpperCase()}`;
}

export const HANDLER_FIELD_LABEL = "Your name (recorded on chain of custody)";
export const HANDLER_FIELD_HINT =
  "Who is performing this action. Written into the custody log as the actor for each step.";
