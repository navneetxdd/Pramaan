import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

/**
 * Accessible tooltip built on @radix-ui/react-tooltip, which was already a
 * dependency but had never been wired up.
 *
 * The native `title` attribute is the wrong tool for forensic detail: it waits
 * about a second, cannot be styled or line-broken, is truncated by some
 * platforms, and is unreachable by keyboard. The confidence-basis sentence and
 * the allocation explanation are the two places an examiner most needs to read
 * a full paragraph, so they get a real popover — keyboard focusable, escapable,
 * and announced to assistive tech.
 */

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({
  content,
  children,
  side = "top",
  className,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}) {
  if (!content) return <>{children}</>;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          className={cn(
            "z-50 max-w-xs rounded-md border border-[var(--border-default)] bg-[var(--surface-2)] px-2.5 py-2",
            "text-[11.5px] leading-relaxed text-[var(--text-secondary)]",
            "shadow-[0_8px_24px_-8px_rgba(15,23,42,0.35)]",
            "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0",
            className,
          )}
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-[var(--surface-2)]" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
