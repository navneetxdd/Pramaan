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
    <section className="visily-hero-dark">
      <div className="visily-hero-dark-bg" aria-hidden />
      <div className="visily-hero-dark-pattern" aria-hidden />
      <div className="relative z-[1] flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="visily-badge visily-badge-active">{badge}</span>
            <span className="mono text-[10px] uppercase tracking-wider text-[var(--text-muted-on-dark)]">
              {since}
            </span>
          </div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-[var(--text-on-dark)]">
            {title}
          </h1>
          <p className="max-w-xl text-[13px] leading-relaxed text-[var(--text-muted-on-dark)]">
            {description}
          </p>
          <dl className="grid gap-3 sm:grid-cols-2">
            {meta.map((item) => (
              <div key={item.label}>
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted-on-dark)]">
                  {item.label}
                </dt>
                <dd
                  className="mono mt-0.5 text-[12px] font-medium"
                  style={{
                    color: item.danger ? "#fca5a5" : "var(--text-on-dark)",
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
            <Button
              asChild
              variant="secondary"
              className="border-white/20 bg-white/10 text-white hover:bg-white/15"
            >
              <Link to={secondaryAction.to}>{secondaryAction.label}</Link>
            </Button>
          ) : secondaryAction?.onClick ? (
            <Button
              variant="secondary"
              className="border-white/20 bg-white/10 text-white hover:bg-white/15"
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </Button>
          ) : null}
          {primaryAction ? (
            <Button
              asChild
              className="bg-[var(--accent-500)] hover:bg-[var(--accent-400)]"
            >
              <Link to={primaryAction.to}>{primaryAction.label}</Link>
            </Button>
          ) : null}
          {extra}
        </div>
      </div>
    </section>
  );
}
