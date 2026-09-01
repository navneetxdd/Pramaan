import { cn } from "@/lib/utils";

export function RadarSweep({
  active,
  label,
  className,
}: {
  active: boolean;
  label?: string | null;
  className?: string;
}) {
  return (
    <div className={cn("relative h-20 w-20", className)}>
      <svg viewBox="0 0 80 80" className="h-full w-full">
        <circle cx="40" cy="40" r="36" fill="var(--surface-3)" stroke="var(--border-default)" strokeWidth="1" />
        <circle cx="40" cy="40" r="24" fill="none" stroke="var(--border-subtle)" strokeWidth="1" />
        <circle cx="40" cy="40" r="12" fill="none" stroke="var(--border-subtle)" strokeWidth="1" />
        {active ? (
          <g className="origin-[40px_40px] animate-[spin_2s_linear_infinite]">
            <path d="M40 40 L40 6 A34 34 0 0 1 74 40 Z" fill="var(--accent-glow)" opacity="0.5" />
          </g>
        ) : null}
        <circle cx="40" cy="40" r="2" fill="var(--accent-500)" />
      </svg>
      {label ? (
        <p className="absolute -bottom-5 left-1/2 w-max -translate-x-1/2 font-mono text-[10px] text-[var(--status-success)]">
          {label}
        </p>
      ) : null}
    </div>
  );
}
