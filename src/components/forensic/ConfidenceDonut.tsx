import { cn } from "@/lib/utils";

type ConfidenceDonutProps = {
  high: number;
  medium: number;
  low: number;
  size?: number;
};

export function ConfidenceDonut({ high, medium, low, size = 120 }: ConfidenceDonutProps) {
  const total = Math.max(high + medium + low, 1);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const segments = [
    { value: high, color: "var(--confidence-high)" },
    { value: medium, color: "var(--confidence-medium)" },
    { value: low, color: "var(--confidence-low)" },
  ];
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 100 100" aria-label="Confidence tier distribution">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--surface-4)" strokeWidth="10" />
        {segments.map((segment) => {
          const length = (segment.value / total) * circumference;
          const dash = `${length} ${circumference - length}`;
          const element = (
            <circle
              key={segment.color}
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth="10"
              strokeDasharray={dash}
              strokeDashoffset={-offset}
              transform="rotate(-90 50 50)"
            />
          );
          offset += length;
          return element;
        })}
        <text x="50" y="48" textAnchor="middle" className="fill-[var(--text-primary)] text-[14px] font-semibold">
          {total}
        </text>
        <text x="50" y="62" textAnchor="middle" className="fill-[var(--text-tertiary)] text-[8px]">
          segments
        </text>
      </svg>
      <div className="grid w-full gap-1 text-[11px]">
        {[
          ["High", high, "var(--confidence-high)"],
          ["Medium", medium, "var(--confidence-medium)"],
          ["Low", low, "var(--confidence-low)"],
        ].map(([label, count, color]) => (
          <div key={String(label)} className="flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: String(color) }} />
              {label}
            </span>
            <span className={cn("mono font-semibold")}>{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function logTone(line: string): string {
  if (/dual_signature|hkvi_block_4|honeywell_index_4|honeywell_format_carve_4/.test(line)) {
    return "text-[var(--status-success)]";
  }
  if (/header_footer|expired|header-only/.test(line)) {
    return "text-[var(--status-warning)]";
  }
  if (/carve|unreferenced|h264_nal/.test(line)) {
    return "text-[var(--text-tertiary)]";
  }
  return "text-[var(--text-secondary)]";
}

export function RecoveryLogPanel({ lines }: { lines: string[] }) {
  return (
    <pre className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed">
      {lines.length === 0 ? (
        <span className="text-[var(--text-tertiary)]">Log output appears when a recovery job runs.</span>
      ) : (
        lines.map((line, index) => (
          <div key={`${index}-${line.slice(0, 24)}`} className={logTone(line)}>
            {line}
          </div>
        ))
      )}
    </pre>
  );
}
