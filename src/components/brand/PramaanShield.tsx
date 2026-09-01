import { cn } from "@/lib/utils";

type PramaanShieldProps = {
  className?: string;
};

/** Visily-inspired shield mark for sidebar branding. */
export function PramaanShield({ className }: PramaanShieldProps) {
  return (
    <div
      className={cn(
        "flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--accent-500)] shadow-[0_0_20px_var(--accent-glow)]",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" aria-hidden>
        <path
          fill="currentColor"
          d="M12 2 4 5v6c0 5.25 3.4 10.15 8 11 4.6-.85 8-5.75 8-11V5l-8-3Zm-1 14.5-3.5-3.5 1.4-1.4 2.1 2.1 4.6-4.6 1.4 1.4-6 6Z"
        />
      </svg>
    </div>
  );
}
