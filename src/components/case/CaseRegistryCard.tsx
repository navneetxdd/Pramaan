import { Link } from "react-router-dom";
import { ChevronRight, HardDrive, User } from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { formatCaseRef } from "@/lib/caseRegistry";
import { pushRecentCase } from "@/lib/recentCases";

export type CaseRegistryRow = {
  id: string;
  name: string;
  examiner_name: string;
  created_at: string;
  notes?: string | null;
  evidence_count: number;
  total_bytes: number;
  recovery_jobs: number;
};

export function CaseRegistryCard({ item }: { item: CaseRegistryRow }) {
  const opened = new Date(item.created_at);
  const hasEvidence = item.evidence_count > 0;

  return (
    <Link
      to={`/cases/${item.id}`}
      onClick={() => pushRecentCase(item.id)}
      className="group block rounded-lg border border-[var(--border-subtle)] bg-white p-4 shadow-sm transition hover:border-[var(--accent-500)]/40 hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="mono text-[10px] font-semibold uppercase tracking-wider text-[var(--accent-600)]">
            {formatCaseRef(item.id)}
          </p>
          <h2 className="mt-1 truncate text-[16px] font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent-600)]">
            {item.name}
          </h2>
          {item.notes ? (
            <p className="mt-1 line-clamp-2 text-[12px] text-[var(--text-secondary)]">
              {item.notes}
            </p>
          ) : null}
        </div>
        <ChevronRight className="mt-1 h-5 w-5 shrink-0 text-[var(--text-tertiary)] group-hover:text-[var(--accent-500)]" />
      </div>

      <dl className="mt-4 grid gap-2 sm:grid-cols-2">
        <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
          <User className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" />
          <div>
            <dt className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Case handler
            </dt>
            <dd className="font-medium text-[var(--text-primary)]">
              {item.examiner_name}
            </dd>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
          <HardDrive className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" />
          <div>
            <dt className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Evidence
            </dt>
            <dd className="font-medium text-[var(--text-primary)]">
              {hasEvidence
                ? `${item.evidence_count} item${item.evidence_count === 1 ? "" : "s"} · ${formatBytes(item.total_bytes)}`
                : "None yet — start at Acquisition"}
            </dd>
          </div>
        </div>
      </dl>

      <div
        className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            hasEvidence
              ? "bg-emerald-50 text-emerald-800"
              : "bg-amber-50 text-amber-900"
          }`}
        >
          {hasEvidence ? "In progress" : "Awaiting evidence"}
        </span>
        {item.recovery_jobs > 0 ? (
          <span className="text-[10px] text-[var(--text-tertiary)]">
            {item.recovery_jobs} recovery run
            {item.recovery_jobs === 1 ? "" : "s"}
          </span>
        ) : null}
        <span className="ml-auto text-[11px] text-[var(--text-tertiary)]">
          Opened{" "}
          {opened.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </span>
      </div>
    </Link>
  );
}
