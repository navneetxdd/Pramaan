import { cn } from "@/lib/utils";

/**
 * Loading placeholder. Deliberately plain: a resting surface tone and the
 * standard pulse, so "still loading" is legible without implying that anything
 * has been measured yet.
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded bg-[var(--surface-4)]", className)}
      {...props}
    />
  );
}
