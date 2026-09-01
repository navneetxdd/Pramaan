import { PramaanMark } from "@/components/brand/PramaanMark";
import { cn } from "@/lib/utils";

type PramaanLogoProps = {
  className?: string;
  markClassName?: string;
  showTagline?: boolean;
  compact?: boolean;
};

export function PramaanLogo({
  className,
  markClassName,
  showTagline = true,
  compact = false,
}: PramaanLogoProps) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <PramaanMark
        variant="brand"
        className={cn(compact ? "h-7 w-7" : "h-9 w-9", markClassName)}
      />
      {!compact ? (
        <div className="min-w-0 leading-none">
          <p
            className="text-[17px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]"
            style={{ fontFeatureSettings: '"ss01" 1' }}
          >
            Pramaan
          </p>
          {showTagline ? (
            <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
              Forensic workstation
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
