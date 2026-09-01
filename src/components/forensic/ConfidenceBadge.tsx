import { cn } from "@/lib/utils";

type ConfidenceTier = "high" | "medium" | "low" | string;

const tierColor: Record<string, string> = {
  high: "var(--confidence-high)",
  medium: "var(--confidence-medium)",
  low: "var(--confidence-low)",
};

export function ConfidenceBadge({
  tier,
  label,
  className,
}: {
  tier: ConfidenceTier;
  label?: string;
  className?: string;
}) {
  const key = tier.toLowerCase();
  const color = tierColor[key] ?? "var(--text-tertiary)";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[11px] uppercase",
        className,
      )}
      style={{ color }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: color }}
      />
      {label ?? tier}
    </span>
  );
}
