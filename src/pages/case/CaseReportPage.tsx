import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api } from "@/lib/api";
import { isNotFound } from "@/lib/apiError";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function CaseReportPage() {
  const { caseId, workspace } = useCaseContext();
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [fingerprint, setFingerprint] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    void Promise.all([api.report(caseId), api.version()])
      .then(([report, version]) => {
        setSummary(report);
        setFingerprint(version.signing_certificate_fingerprint ?? "");
      })
      .catch((err) => {
        if (isNotFound(err)) {
          setLoadError("Case not found.");
          return;
        }
        const message =
          err instanceof Error ? err.message : "Report load failed";
        setLoadError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  }, [caseId]);

  const evidenceCount = workspace?.evidence.length ?? 0;
  const jobCount =
    workspace?.jobs.filter((j) => j.status === "completed").length ?? 0;
  const custodyCount = workspace?.custody.length ?? 0;
  const hasMethodology = Boolean(summary && typeof summary === "object");
  const chainOk = Boolean(
    (summary as { custody_chain_valid?: { ok?: boolean } } | null)
      ?.custody_chain_valid?.ok,
  );

  const sections = [
    {
      label: "Device summary",
      count: evidenceCount,
      active: evidenceCount > 0,
    },
    { label: "Recovered sequences", count: jobCount, active: jobCount > 0 },
    {
      label: "Methodology",
      count: hasMethodology ? 1 : 0,
      active: hasMethodology,
      hideCount: true,
    },
    {
      label: "Custody log appendix",
      count: custodyCount,
      active: custodyCount > 0,
    },
    {
      label: `Custody chain ${chainOk ? "intact" : "check required"}`,
      count: chainOk ? 1 : 0,
      active: chainOk,
      hideCount: true,
      warning: !chainOk,
    },
  ];

  const completedCount = sections.filter((s) => s.active).length;
  const totalCount = sections.length;
  const progressPercent =
    totalCount === 0 ? 0 : (completedCount / totalCount) * 100;

  return (
    <div className="flex flex-col gap-3">
      {/* 1. Header Card */}
      <section className="visily-card p-5 lg:p-6">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className="border-[var(--accent-500)] text-[var(--accent-500)] uppercase tracking-wider text-[10px]"
              >
                Case deliverable
              </Badge>
              {fingerprint && (
                <code className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-xs text-[var(--text-secondary)] border border-[var(--border-subtle)]">
                  Sig: {fingerprint.slice(0, 24)}… (self-signed integrity only)
                </code>
              )}
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Forensic report
              </h1>
              <p className="text-sm text-[var(--text-secondary)] mt-1">
                Live preview of the generated Section 63 certificate.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 mt-2 md:mt-0">
            <Button asChild variant="secondary">
              <a
                href={api.reportHtmlUrl(caseId)}
                target="_blank"
                rel="noreferrer"
              >
                Open HTML
              </a>
            </Button>
            <Button asChild>
              <a href={api.reportPdfUrl(caseId)} download>
                Download PDF
              </a>
            </Button>
          </div>
        </div>
      </section>

      <div className="grid h-[calc(100vh-180px)] min-h-[700px] gap-3 lg:grid-cols-[260px_1fr]">
        {/* 2. Report Sections Checklist */}
        <section className="visily-card flex flex-col overflow-hidden">
          <div className="p-4 border-b border-[var(--border-subtle)] bg-[var(--surface-3)]">
            <div className="mb-2 flex items-center justify-between">
              <span className="visily-card-title">Report sections</span>
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {completedCount} of {totalCount}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--border-subtle)]">
              <div
                className="h-full bg-[var(--accent-500)] transition-all duration-500 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          <div className="flex-1 space-y-3.5 p-4 overflow-y-auto">
            {sections.map((sec, i) => (
              <div
                key={i}
                className={`flex items-center gap-3 text-[13px] ${
                  sec.active
                    ? "text-[var(--text-primary)]"
                    : "text-[var(--text-tertiary)]"
                }`}
              >
                {sec.active ? (
                  <svg
                    className="h-4 w-4 shrink-0 text-[var(--status-success)]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : sec.warning ? (
                  <svg
                    className="h-4 w-4 shrink-0 text-[var(--status-warning)]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                  </svg>
                ) : (
                  <div className="flex h-4 w-4 shrink-0 items-center justify-center">
                    <div className="h-[2px] w-2.5 bg-[var(--border-subtle)]" />
                  </div>
                )}
                <span className="flex-1 truncate">{sec.label}</span>
                {!sec.hideCount && (
                  <span className="rounded bg-[var(--surface-3)] border border-[var(--border-subtle)] px-1.5 font-mono text-[11px] text-[var(--text-secondary)]">
                    {sec.count}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Footer inside sections panel */}
          {!loading && summary && (
            <div className="mt-auto space-y-1.5 border-t border-[var(--border-subtle)] bg-[var(--surface-3)] p-4 text-[11px]">
              <div className="flex justify-between gap-2">
                <span className="text-[var(--text-tertiary)]">Segments</span>
                <span className="font-mono text-[var(--text-secondary)]">
                  {String((summary as any).total_segments_recovered ?? 0)}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-[var(--text-tertiary)]">Generated</span>
                <span className="font-mono truncate text-[var(--text-secondary)]">
                  {String((summary as any).generated_at ?? "—").slice(0, 19)}
                </span>
              </div>
            </div>
          )}
        </section>

        {/* 3. Preview Panel */}
        <section className="visily-card flex flex-col overflow-hidden">
          <div className="visily-card-header shrink-0 shadow-sm z-10">
            <span className="visily-card-title">HTML preview</span>
          </div>

          <div className="flex-1 bg-slate-50/60 p-4 sm:p-6 md:p-8">
            {loading ? (
              <div className="mx-auto h-full max-w-[850px] animate-pulse space-y-4 border border-slate-200/60 bg-white p-8 shadow-sm">
                <div className="h-8 w-1/3 rounded bg-slate-100" />
                <div className="h-4 w-full rounded bg-slate-100" />
                <div className="h-[400px] w-full rounded bg-slate-100" />
              </div>
            ) : loadError ? (
              <div className="mx-auto max-w-[850px] border border-slate-200/60 bg-white p-8 shadow-sm">
                <p className="text-[13px] text-[var(--status-danger)]">
                  {loadError}
                </p>
              </div>
            ) : (
              <div className="mx-auto h-full max-w-[850px] border border-slate-200/60 bg-white shadow-sm ring-1 ring-slate-900/5">
                <iframe
                  title="Forensic report preview"
                  src={api.reportHtmlUrl(caseId)}
                  className="block h-full w-full border-0"
                />
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
