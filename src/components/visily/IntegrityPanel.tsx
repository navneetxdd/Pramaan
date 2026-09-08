import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ChainLinkIndicator,
  type ChainLinkState,
} from "@/components/forensic/ChainLinkIndicator";

type IntegrityPanelProps = {
  state: ChainLinkState;
  lastAudit?: string;
  /** Database id of the first custody row that fails verification, when the
   * chain is broken. Shown so the examiner sees the break point here, not only
   * on the Custody page. */
  brokenRowId?: number | null;
  onVerify?: () => void;
};

export function IntegrityPanel({
  state,
  lastAudit,
  brokenRowId,
  onVerify,
}: IntegrityPanelProps) {
  const intact = state === "intact";
  const broken = state === "broken";

  return (
    <div className="visily-card h-full">
      <div className="visily-card-header">
        <span className="visily-card-title">Chain of custody</span>
        <ShieldCheck className="h-4 w-4 text-[var(--accent-400)]" />
      </div>
      <div className="space-y-4 p-4">
        <div className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2">
          <div className="flex items-center gap-2">
            <ChainLinkIndicator state={state} />
            <span className="text-[12px] font-medium text-[var(--text-primary)]">
              Hash chain
            </span>
          </div>
          <span
            className={
              intact
                ? "visily-badge visily-badge-success"
                : "visily-badge visily-badge-danger"
            }
          >
            {intact ? "Intact" : state === "checking" ? "Checking" : "Broken"}
          </span>
        </div>
        {broken ? (
          <p className="text-[11px] text-[var(--status-danger)]">
            {brokenRowId != null
              ? `First failing row: custody id ${brokenRowId}. Rows before it still verify. See Custody for the full log.`
              : "Verification failed but the exact break point could not be determined. See Custody."}
          </p>
        ) : null}
        {lastAudit ? (
          <p className="mono text-[11px] text-[var(--text-tertiary)]">
            Last audit: {lastAudit}
          </p>
        ) : null}
        {onVerify ? (
          <Button
            variant="secondary"
            size="sm"
            className="w-full"
            onClick={onVerify}
          >
            Verify custody chain
          </Button>
        ) : null}
      </div>
    </div>
  );
}
