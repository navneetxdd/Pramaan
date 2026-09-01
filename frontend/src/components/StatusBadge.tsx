import { cn } from "@/lib/utils";

type Props = {
  status: string;
  className?: string;
};

const map: Record<string, string> = {
  open: "border-solved-line bg-solved-soft text-solved",
  running: "border-accent-line bg-accent-soft text-accent",
  completed: "border-solved-line bg-solved-soft text-solved",
  failed: "border-danger/40 bg-danger-soft text-danger",
};

export function StatusBadge({ status, className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium uppercase tracking-wide",
        map[status] ?? "border-hairline bg-raised text-ink-muted",
        className,
      )}
    >
      {status}
    </span>
  );
}
