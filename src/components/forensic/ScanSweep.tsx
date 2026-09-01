import { cn } from "@/lib/utils";

export function ScanSweep({ progress, className }: { progress: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, progress));
  return (
    <div
      className={cn("relative h-16 w-16 overflow-hidden rounded-full border border-[var(--border-default)] bg-[var(--surface-3)]", className)}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <svg viewBox="0 0 64 64" className="h-full w-full">
        <circle cx="32" cy="32" r="28" fill="none" stroke="var(--border-subtle)" strokeWidth="2" />
        <line
          x1="32"
          y1="32"
          x2="32"
          y2="8"
          stroke="var(--accent-500)"
          strokeWidth="2"
          strokeLinecap="round"
          style={{
            transform: `rotate(${(pct / 100) * 360}deg)`,
            transformOrigin: "32px 32px",
            transition: "transform 120ms linear",
          }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-mono text-[11px] text-[var(--text-secondary)]">
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}
