import type { ReactNode } from "react";

type PageHeaderProps = {
  kicker?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
};

export function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
}: PageHeaderProps) {
  return (
    <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-0)] px-5 py-4">
      {kicker ? (
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--accent-600)]">
          {kicker}
        </p>
      ) : null}
      <div className="mt-1 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-semibold leading-tight text-[var(--text-primary)]">
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[var(--text-secondary)]">
              {subtitle}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>
        ) : null}
      </div>
    </header>
  );
}
