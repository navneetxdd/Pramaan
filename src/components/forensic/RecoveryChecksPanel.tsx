import { useMemo } from "react";
import type { Segment } from "@/lib/api";
import {
  collectChecks,
  strengthColor,
  strengthCounts,
  type Strength,
} from "@/lib/checks";

/**
 * What the parser actually verified, for the current segment set.
 *
 * Replaces the former confidence donut. That donut charted a number the backend
 * fabricated (`0.92 / 0.7 / 0.55`), which had already destroyed the parser's
 * real value. Nothing here is scored, averaged or weighted: each row is a count
 * of segments whose parser recorded that check as passing.
 */
export function RecoveryChecksPanel({ segments }: { segments: Segment[] }) {
  const checks = useMemo(() => collectChecks(segments), [segments]);
  const strengths = useMemo(() => strengthCounts(segments), [segments]);

  if (segments.length === 0) {
    return (
      <p className="text-[12px] text-[var(--text-tertiary)]">
        Run recovery to see which parser checks passed.
      </p>
    );
  }

  const booleans = checks.filter((c) => c.kind === "boolean");
  const values = checks.filter((c) => c.kind === "value");

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        {(["strong", "weak", "none"] as Strength[])
          .filter((s) => strengths[s] > 0)
          .map((s) => (
            <div
              key={s}
              className="flex items-baseline justify-between text-[12px]"
            >
              <span
                className="font-semibold uppercase"
                style={{ color: strengthColor(s) }}
                title={
                  s === "strong"
                    ? "A filesystem/index structure was parsed for this segment"
                    : s === "weak"
                      ? "Signature evidence only — no structure parsed"
                      : "No usable parser evidence"
                }
              >
                {s}
              </span>
              <span className="mono">
                {strengths[s]}/{segments.length}
              </span>
            </div>
          ))}
      </div>

      {booleans.length > 0 ? (
        <div className="space-y-1 border-t border-[var(--border-subtle)] pt-2">
          {booleans.map((check) => {
            const ok = check.passed === check.total;
            return (
              <div
                key={check.key}
                className="flex items-baseline justify-between gap-2 text-[11px]"
              >
                <span className="flex items-center gap-1.5 text-[var(--text-secondary)]">
                  <span
                    aria-hidden="true"
                    style={{
                      color: ok
                        ? "var(--status-success)"
                        : "var(--status-warning)",
                    }}
                  >
                    {ok ? "✓" : "!"}
                  </span>
                  {check.label}
                </span>
                <span className="mono whitespace-nowrap text-[var(--text-tertiary)]">
                  {check.passed}/{check.total}
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      {values.length > 0 ? (
        <div className="space-y-1 border-t border-[var(--border-subtle)] pt-2">
          {values.map((check) => (
            <div key={check.key} className="text-[11px]">
              <span className="text-[var(--text-tertiary)]">{check.label}</span>
              <div className="mono break-all text-[var(--text-secondary)]">
                {check.values.length === 1
                  ? check.values[0]
                  : `${check.values.length} distinct`}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
