import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

type HeroBannerProps = {
  badge: string;
  since: string;
  title: string;
  description: string;
  meta: Array<{ label: string; value: string; danger?: boolean }>;
  primaryAction?: { label: string; to: string };
  secondaryAction?: { label: string; to?: string; onClick?: () => void };
  extra?: ReactNode;
};

export function HeroBanner({
  badge,
  since,
  title,
  description,
  meta,
  primaryAction,
  secondaryAction,
  extra,
}: HeroBannerProps) {
  return (
    <section className="border-b border-[var(--border-subtle)] bg-[var(--surface-0)] px-5 py-5">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="visily-badge visily-badge-active">{badge}</span>
            <span className="mono text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">
              {since}
            </span>
          </div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-[var(--text-primary)]">
            {title}
          </h1>
          <p className="max-w-xl text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {description}
          </p>
          <dl className="grid gap-3 sm:grid-cols-2">
            {meta.map((item) => (
              <div key={item.label}>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                  {item.label}
                </dt>
                <dd
                  className="mono mt-0.5 text-[12px] font-medium"
                  style={{
                    color: item.danger
                      ? "var(--status-danger)"
                      : "var(--text-primary)",
                  }}
                >
                  {item.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {secondaryAction?.to ? (
            <Button asChild variant="secondary">
              <Link to={secondaryAction.to}>{secondaryAction.label}</Link>
            </Button>
          ) : secondaryAction?.onClick ? (
            <Button variant="secondary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          ) : null}
          {primaryAction ? (
            <Button asChild>
              <Link to={primaryAction.to}>{primaryAction.label}</Link>
            </Button>
          ) : null}
          {extra}
        </div>
      </div>
    </section>
  );
}
