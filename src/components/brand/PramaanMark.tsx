import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

type PramaanMarkProps = SVGProps<SVGSVGElement> & {
  variant?: "on-color" | "mono" | "brand";
};

/** Compact shutter mark — crisp at 16–32px. */
export function PramaanMark({ className, variant = "mono", ...props }: PramaanMarkProps) {
  const stroke =
    variant === "on-color" ? "#ffffff" : variant === "brand" ? "var(--accent-500)" : "currentColor";
  const fill =
    variant === "on-color" ? "#ffffff" : variant === "brand" ? "var(--accent-500)" : "currentColor";

  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className={cn("size-6 shrink-0", className)}
      shapeRendering="geometricPrecision"
      {...props}
    >
      <g stroke={stroke} strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="12" x2="12" y2="6.5" strokeWidth="1.35" />
        <line x1="12" y1="12" x2="16.2" y2="8.2" strokeWidth="1.35" />
        <line x1="12" y1="12" x2="16.2" y2="15.8" strokeWidth="1.35" />
        <line x1="12" y1="12" x2="12" y2="17.5" strokeWidth="1.35" />
        <line x1="12" y1="12" x2="7.8" y2="15.8" strokeWidth="1.35" />
        <line x1="12" y1="12" x2="7.8" y2="8.2" strokeWidth="1.35" opacity="0.45" strokeDasharray="2 2" />
      </g>
      <circle cx="12" cy="12" r="1.35" fill={fill} />
    </svg>
  );
}
