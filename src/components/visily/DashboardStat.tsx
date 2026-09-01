import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type DashboardStatProps = {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  tone?: "default" | "success" | "danger" | "info";
};

export function DashboardStat({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: DashboardStatProps) {
  const toneClass =
    tone === "success"
      ? "text-[var(--status-success)]"
      : tone === "danger"
        ? "text-[var(--status-danger)]"
        : tone === "info"
          ? "text-[var(--status-info)]"
          : "text-[var(--accent-400)]";

  return (
    <div className="visily-stat-card">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="visily-stat-value">{value}</p>
          <p className="visily-stat-label">{label}</p>
          {hint ? (
            <p className="mono mt-1 text-[10px] text-[var(--text-tertiary)]">
              {hint}
            </p>
          ) : null}
        </div>
        <div className={cn("rounded-md bg-[var(--surface-4)] p-2", toneClass)}>
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </div>
      </div>
    </div>
  );
}
