import { cn } from "@/lib/utils";

export type ChainLinkState = "intact" | "broken" | "checking" | "unknown";

export function ChainLinkIndicator({ state, className }: { state: ChainLinkState; className?: string }) {
  const color =
    state === "intact"
      ? "var(--status-success)"
      : state === "broken"
        ? "var(--status-danger)"
        : state === "checking"
          ? "var(--status-warning)"
          : "var(--text-tertiary)";

  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} title={`Custody chain: ${state}`}>
      <svg width="20" height="12" viewBox="0 0 20 12" aria-hidden>
        <path
          d="M2 6 H7"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          className={state === "checking" ? "animate-pulse" : undefined}
        />
        <path
          d="M13 6 H18"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          className={state === "checking" ? "animate-pulse" : undefined}
        />
        {state === "broken" ? (
          <path d="M8 3 L12 9 M12 3 L8 9" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
        ) : (
          <rect x="7" y="3" width="6" height="6" rx="1" fill="none" stroke={color} strokeWidth="1.5" />
        )}
      </svg>
    </span>
  );
}
