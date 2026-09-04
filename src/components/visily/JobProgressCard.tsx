import { cn } from "@/lib/utils";

type JobProgressCardProps = {
  title: string;
  subtitle: string;
  progress?: number;
  status: "running" | "completed" | "failed" | "idle";
  meta?: string[];
};

export function JobProgressCard({
  title,
  subtitle,
  progress,
  status,
  meta = [],
}: JobProgressCardProps) {
  const pct = progress ?? (status === "completed" ? 100 : 0);

  return (
    <div
      className={cn(
        "visily-job-card",
        status === "running" && "visily-job-card-active",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="mono text-[12px] font-medium text-[var(--text-primary)]">
            {title}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">
            {subtitle}
          </p>
        </div>
        <span
          className={cn(
            "visily-badge",
            status === "completed" && "visily-badge-success",
            status === "running" && "visily-badge-active",
            status === "failed" && "visily-badge-danger",
            status === "idle" && "visily-badge-neutral",
          )}
        >
          {status === "completed"
            ? "Completed"
            : status === "running"
              ? `${pct.toFixed(0)}%`
              : status}
        </span>
      </div>
      {status === "running" ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[var(--surface-4)]">
          <div
            className="h-full rounded-full bg-[var(--accent-400)] transition-all duration-500"
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      ) : null}
      {meta.length > 0 ? (
        <ul className="mt-3 space-y-1">
          {meta.map((line) => (
            <li
              key={line}
              className="mono text-[10px] text-[var(--text-tertiary)]"
            >
              {line}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
