import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "success" | "warning" | "danger" | "info" | "outline";
};

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const styles = {
    default:
      "bg-[var(--surface-3)] text-[var(--text-secondary)] border-[var(--border-subtle)]",
    success:
      "bg-[rgba(59,166,118,0.15)] text-[var(--status-success)] border-[var(--status-success)]",
    warning:
      "bg-[rgba(217,164,65,0.15)] text-[var(--status-warning)] border-[var(--status-warning)]",
    danger:
      "bg-[rgba(214,88,79,0.15)] text-[var(--status-danger)] border-[var(--status-danger)]",
    info: "bg-[rgba(74,159,216,0.15)] text-[var(--status-info)] border-[var(--status-info)]",
    outline:
      "bg-transparent text-[var(--text-secondary)] border-[var(--border-default)]",
  }[variant];

  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 font-mono text-[11px] border",
        styles,
        className,
      )}
      {...props}
    />
  );
}
