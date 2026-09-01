import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type IdentificationReport } from "@/lib/api";
import { capabilityTierLabel } from "@/lib/integrity";
import { RadarSweep } from "@/components/forensic/RadarSweep";
import { ConfidenceBadge } from "@/components/forensic/ConfidenceBadge";
import { Button } from "@/components/ui/button";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { Fingerprint, Layers, Shield } from "lucide-react";
import { formatBytes } from "@/lib/utils";

function formatHexDump(hex: string, ascii: string, offset: number): string {
  const bytes = hex.match(/.{1,2}/g) ?? [];
  const lines: string[] = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const slice = bytes.slice(i, i + 16);
    const addr = (offset + i).toString(16).padStart(8, "0");
    const hexPart = slice.map((b) => b.toUpperCase()).join(" ").padEnd(47, " ");
    const asciiPart = ascii.slice(i, i + 16);
    lines.push(`${addr}  ${hexPart}  ${asciiPart}`);
  }
  return lines.join("\n");
}

export function CaseDeviceIdPage() {
  const { workspace, refresh } = useCaseContext();
  const [deviceId, setDeviceId] = useState("");
  const [report, setReport] = useState<IdentificationReport | null>(null);
  const [scanning, setScanning] = useState(false);
  const [hexOffset, setHexOffset] = useState(0);
  const [hexDump, setHexDump] = useState<string | null>(null);
  const [hexLoading, setHexLoading] = useState(false);

  const evidence = workspace?.evidence ?? [];

  useEffect(() => {
    if (evidence[0] && !deviceId) {
      setDeviceId(evidence[0].id);
      setReport(evidence[0].identification ?? null);
    }
  }, [evidence, deviceId]);

  useEffect(() => {
    if (!deviceId) {
      setHexDump(null);
      return;
    }
    setHexLoading(true);
    void api
      .readDeviceBytes(deviceId, hexOffset, 256)
      .then((r) => setHexDump(formatHexDump(r.hex, r.ascii, r.offset)))
      .catch(() => setHexDump(null))
      .finally(() => setHexLoading(false));
  }, [deviceId, hexOffset]);

  async function runIdentify() {
    if (!deviceId) return;
    setScanning(true);
    try {
      const result = await api.identify(deviceId);
      setReport(result);
      toast.success(`Detected: ${result.recommended_adapter}`);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Identification failed", { duration: Infinity });
    } finally {
      setScanning(false);
    }
  }

  const topHit = report?.hits[0];
  const identifiedCount = evidence.filter((e) => e.identification?.recommended_adapter).length;
  const selectedEvidence = evidence.find((e) => e.id === deviceId);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">OEM analysis</p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Device identification</h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Signature trace, capability tier, and bounded hex preview — routing hints only, not field validation.
            </p>
          </div>
          <Button disabled={!deviceId || scanning} onClick={() => void runIdentify()}>
            Run identification
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <DashboardStat label="Evidence items" value={String(evidence.length)} icon={Layers} />
        <DashboardStat label="Identified" value={String(identifiedCount)} icon={Fingerprint} tone="info" />
        <DashboardStat
          label="Recommended adapter"
          value={report?.recommended_adapter ?? "—"}
          icon={Shield}
          tone={topHit ? "success" : undefined}
        />
      </div>

      {evidence.length === 0 ? (
        <section className="visily-card p-8 text-[13px] text-[var(--text-secondary)]">
          No evidence to analyze. Acquire an image on the Acquisition screen first.
        </section>
      ) : (
        <div className="grid min-h-[360px] gap-3 lg:grid-cols-[220px_1fr_240px]">
          <section className="visily-card p-3">
            <p className="visily-card-title mb-2 text-[11px]">Imaged devices</p>
            <ul className="space-y-1">
              {evidence.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    className={`w-full rounded px-2 py-1.5 text-left text-[12px] ${
                      deviceId === e.id ? "bg-[var(--accent-soft)] text-[var(--accent-500)]" : "hover:bg-[var(--surface-3)]"
                    }`}
                    onClick={() => {
                      setDeviceId(e.id);
                      setReport(e.identification ?? null);
                      setHexOffset(0);
                    }}
                  >
                    {e.filename}
                  </button>
                </li>
              ))}
            </ul>
            {selectedEvidence ? (
              <p className="mono mt-3 text-[10px] text-[var(--text-tertiary)]">
                {formatBytes(selectedEvidence.size_bytes)} · sample covers first{" "}
                {Math.min(64 * 1024 * 1024, selectedEvidence.size_bytes) / (1024 * 1024)} MiB
              </p>
            ) : null}
          </section>

          <section className="visily-card p-3">
            <p className="visily-card-title mb-2 text-[11px]">Detection trace</p>
            <div className="flex items-start gap-4">
              <RadarSweep active={scanning} label={scanning ? null : topHit?.adapter ?? null} />
              <div className="min-w-0 flex-1">
                {!report ? (
                  <p className="text-[13px] text-[var(--text-tertiary)]">Select a device and run identification.</p>
                ) : (
                  <ul className="space-y-2 font-mono text-[12px]">
                    {report.hits.map((hit) => (
                      <li key={`${hit.vendor}-${hit.adapter}`} className="rounded border border-[var(--border-subtle)] px-2 py-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span>{hit.vendor}</span>
                          <ConfidenceBadge
                            tier={hit.confidence >= 0.8 ? "high" : hit.confidence >= 0.5 ? "medium" : "low"}
                          />
                        </div>
                        <p className="mt-1 text-[var(--text-tertiary)]">{hit.markers.join(", ")}</p>
                        {hit.capability_tier ? (
                          <p className="mt-1 text-[10px] uppercase tracking-wide text-[var(--accent-500)]">
                            {capabilityTierLabel(hit.capability_tier)}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="visily-card-title text-[11px]">Hex preview (256 B)</p>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" disabled={hexOffset <= 0} onClick={() => setHexOffset((o) => Math.max(0, o - 256))}>
                    −256
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setHexOffset((o) => o + 256)}>
                    +256
                  </Button>
                </div>
              </div>
              <pre className="max-h-40 overflow-auto rounded bg-[var(--surface-3)] p-2 font-mono text-[10px] leading-relaxed text-[var(--text-secondary)]">
                {hexLoading ? "Loading…" : hexDump ?? "Hex preview unavailable"}
              </pre>
            </div>
          </section>

          <section className="visily-card p-3">
            <p className="visily-card-title mb-2 text-[11px]">Filesystem hints</p>
            {(report?.filesystem_hints ?? []).length === 0 ? (
              <p className="text-[12px] text-[var(--text-tertiary)]">Run identification to populate hints.</p>
            ) : (
              <ul className="space-y-1 font-mono text-[11px] text-[var(--text-secondary)]">
                {report?.filesystem_hints.map((h) => (
                  <li key={h.marker}>{h.label}</li>
                ))}
              </ul>
            )}
            {report?.coverage_note ? (
              <p className="mt-3 rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] p-2 text-[11px] text-[var(--text-secondary)]">
                {report.coverage_note}
              </p>
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
