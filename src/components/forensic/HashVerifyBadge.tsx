import { Check, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type HashVerifyState = "pending" | "verified" | "mismatch" | "idle";

export function HashVerifyBadge({ state, className }: { state: HashVerifyState; className?: string }) {
  if (state === "idle") return null;

  const config = {
    pending: { icon: Loader2, color: "var(--status-info)", label: "Verifying…", spin: true },
    verified: { icon: Check, color: "var(--status-success)", label: "Hash verified", spin: false },
    mismatch: { icon: X, color: "var(--status-danger)", label: "Hash mismatch", spin: false },
  }[state];

  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px]",
        className,
      )}
      style={{ borderColor: config.color, color: config.color }}
    >
      <Icon className={cn("h-3.5 w-3.5", config.spin && "animate-spin")} />
      {config.label}
    </span>
  );
}
