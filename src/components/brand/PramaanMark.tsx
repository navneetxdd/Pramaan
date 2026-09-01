import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

type PramaanMarkProps = SVGProps<SVGSVGElement>;

/**
 * Proof shutter — evidence frame, lens blades, one segment recovering, hash bar below.
 * Geometric mark for DVR recovery + chain-of-custody. No fill except anchor dot.
 */
export function PramaanMark({ className, ...props }: PramaanMarkProps) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={cn("size-[22px] shrink-0", className)} {...props}>
      <rect
        x="2.5"
        y="2.5"
        width="15"
        height="15"
        rx="2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
      />

      <g stroke="currentColor" strokeLinecap="round">
        <line x1="10" y1="10" x2="10" y2="5.8" strokeWidth="1" />
        <line x1="10" y1="10" x2="13.6" y2="7.4" strokeWidth="1" />
        <line x1="10" y1="10" x2="13.6" y2="12.6" strokeWidth="1" />
        <line x1="10" y1="10" x2="10" y2="14.2" strokeWidth="1" />
        <line x1="10" y1="10" x2="6.4" y2="12.6" strokeWidth="1" />
        <line
          x1="10"
          y1="10"
          x2="6.4"
          y2="7.4"
          strokeWidth="1"
          strokeDasharray="1.6 1.8"
          strokeOpacity="0.45"
        />
      </g>

      <circle cx="10" cy="10" r="1" fill="currentColor" />

      <path
        d="M5.8 15.2h2M8.4 15.2h2M11 15.2h2"
        stroke="currentColor"
        strokeWidth="0.85"
        strokeLinecap="round"
      />
    </svg>
  );
}
