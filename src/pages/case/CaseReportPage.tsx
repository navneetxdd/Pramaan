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

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">
              Case deliverable
            </p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">
              Forensic report
            </h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Live HTML preview of the signed forensic report.
            </p>
            {fingerprint ? (
              <p className="mono mt-2 text-[10px] text-[var(--text-muted-on-dark)]">
                signature: {fingerprint.slice(0, 24)}… · self-signed integrity
                only
              </p>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button
              asChild
              variant="secondary"
              className="border-white/20 bg-white/10 text-white hover:bg-white/15"
            >
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
      </div>

      <div className="grid min-h-[560px] gap-3 lg:grid-cols-[240px_1fr]">
        <section className="visily-card p-3">
          <p className="visily-card-title mb-2 text-[11px]">Report sections</p>
          <ul className="space-y-1 text-[13px] text-[var(--text-secondary)]">
            <li className="flex items-center gap-2">
              <Badge variant={evidenceCount > 0 ? "success" : "outline"}>
                {evidenceCount > 0 ? "✓" : "—"}
              </Badge>
              Device summary ({evidenceCount})
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={jobCount > 0 ? "success" : "outline"}>
                {jobCount > 0 ? "✓" : "—"}
              </Badge>
              Recovered sequences ({jobCount} jobs)
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={hasMethodology ? "success" : "outline"}>
                {hasMethodology ? "✓" : "—"}
              </Badge>
              Methodology
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={custodyCount > 0 ? "success" : "outline"}>
                {custodyCount > 0 ? "✓" : "—"}
              </Badge>
              Custody log appendix ({custodyCount} events)
            </li>
            <li className="flex items-center gap-2">
              <Badge variant={chainOk ? "success" : "outline"}>
                {chainOk ? "✓" : "!"}
              </Badge>
              Custody chain {chainOk ? "intact" : "check required"}
            </li>
          </ul>
          {!loading && summary ? (
            <dl
              className="mt-4 space-y-1 border-t pt-3 text-[11px]"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-tertiary)]">Segments</dt>
                <dd className="mono">
                  {String(
                    (summary as { total_segments_recovered?: number })
                      .total_segments_recovered ?? 0,
                  )}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-tertiary)]">Generated</dt>
                <dd className="mono truncate">
                  {String(
                    (summary as { generated_at?: string }).generated_at ?? "—",
                  )}
                </dd>
              </div>
            </dl>
          ) : null}
        </section>

        <section className="visily-card overflow-hidden">
          <div className="visily-card-header">
            <span className="visily-card-title">HTML preview</span>
          </div>
          {loading ? (
            <p className="p-6 text-[13px] text-[var(--text-tertiary)]">
              Loading report preview…
            </p>
          ) : loadError ? (
            <p className="p-6 text-[13px] text-[var(--status-danger)]">
              {loadError}
            </p>
          ) : (
            <iframe
              title="Forensic report preview"
              src={api.reportHtmlUrl(caseId)}
              className="h-[640px] w-full border-0 bg-white"
            />
          )}
        </section>
      </div>
    </div>
  );
}
