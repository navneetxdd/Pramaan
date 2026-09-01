import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function CaseReportPage() {
  const { caseId, workspace } = useCaseContext();
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    void api
      .report(caseId)
      .then(setSummary)
      .catch((err) => toast.error(err instanceof Error ? err.message : "Report load failed", { duration: Infinity }))
      .finally(() => setLoading(false));
  }, [caseId]);

  const evidenceCount = workspace?.evidence.length ?? 0;
  const jobCount = workspace?.jobs.filter((j) => j.status === "completed").length ?? 0;
  const custodyCount = workspace?.custody.length ?? 0;
  const hasMethodology = Boolean(summary && typeof summary === "object");

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Case deliverable</p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Forensic report</h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Signed HTML and PDF bundles generated from live case data — methodology, devices, sequences, custody.
            </p>
          </div>
          <div className="flex gap-2">
            <Button asChild variant="secondary" className="border-white/20 bg-white/10 text-white hover:bg-white/15">
              <a href={api.reportHtmlUrl(caseId)} target="_blank" rel="noreferrer">
                Preview HTML
              </a>
            </Button>
            <Button asChild>
              <a href={api.reportPdfUrl(caseId)} download>
                Download PDF
              </a>
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[240px_1fr]">
        <section className="visily-card p-3">
          <p className="visily-card-title mb-2 text-[11px]">Report sections</p>
          <ul className="space-y-1 text-[13px] text-[var(--text-secondary)]">
            <li className="flex items-center gap-2">
              <Badge variant={evidenceCount > 0 ? "success" : "outline"}>{evidenceCount > 0 ? "✓" : "—"}</Badge>
              Device summary ({evidenceCount})
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={jobCount > 0 ? "success" : "outline"}>{jobCount > 0 ? "✓" : "—"}</Badge>
              Recovered sequences ({jobCount} jobs)
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={hasMethodology ? "success" : "outline"}>{hasMethodology ? "✓" : "—"}</Badge>
              Methodology
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={custodyCount > 0 ? "success" : "outline"}>{custodyCount > 0 ? "✓" : "—"}</Badge>
              Custody log appendix ({custodyCount} events)
            </li>
          </ul>
        </section>

        <section className="visily-card p-3">
          <p className="visily-card-title mb-2 text-[11px]">Report metadata</p>
          {loading ? (
            <p className="text-[13px] text-[var(--text-tertiary)]">Loading report metadata…</p>
          ) : summary ? (
            <pre className="max-h-[480px] overflow-auto font-mono text-[11px] text-[var(--text-secondary)]">
              {JSON.stringify(summary, null, 2)}
            </pre>
          ) : (
            <p className="text-[13px] text-[var(--text-secondary)]">Report metadata unavailable.</p>
          )}
        </section>
      </div>
    </div>
  );
}
