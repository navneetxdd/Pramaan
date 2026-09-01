import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ChainLinkIndicator,
  type ChainLinkState,
} from "@/components/forensic/ChainLinkIndicator";

type IntegrityPanelProps = {
  state: ChainLinkState;
  lastAudit?: string;
  witnessHash?: string;
  witnessLabel?: string;
  onVerify?: () => void;
};

export function IntegrityPanel({
  state,
  lastAudit,
  witnessHash,
  witnessLabel = "Chain tip hash",
  onVerify,
}: IntegrityPanelProps) {
  const secure = state === "intact";

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
              Chain of custody
            </span>
          </div>
          <span
            className={
              secure
                ? "visily-badge visily-badge-success"
                : "visily-badge visily-badge-danger"
            }
          >
            {secure ? "Secure" : state === "checking" ? "Checking" : "Alert"}
          </span>
        </div>
        {lastAudit ? (
          <p className="mono text-[11px] text-[var(--text-tertiary)]">
            Last audit: {lastAudit}
          </p>
        ) : null}
        {witnessHash ? (
          <p className="mono truncate text-[10px] text-[var(--text-secondary)]">
            {witnessLabel}: {witnessHash.slice(0, 16)}…
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
