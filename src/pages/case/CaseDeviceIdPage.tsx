import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type IdentificationReport } from "@/lib/api";
import { capabilityTierLabel, validationScopeLabel } from "@/lib/integrity";
import { ConfidenceBadge } from "@/components/forensic/ConfidenceBadge";
import { HexViewer } from "@/components/forensic/HexViewer";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/visily/PageHeader";
import { formatBytes, formatOffset } from "@/lib/utils";

type StructureNode = {
  label: string;
  offset: number;
  size: number;
  type: string;
  meta?: Record<string, unknown>;
  children?: StructureNode[];
};

function flattenNodes(
  nodes: StructureNode[],
  depth = 0,
): Array<{ node: StructureNode; depth: number }> {
  const flat: Array<{ node: StructureNode; depth: number }> = [];

  for (const node of nodes) {
    flat.push({ node, depth });

    if (node.children?.length) {
      flat.push(...flattenNodes(node.children, depth + 1));
    }
  }

  return flat;
}

export function CaseDeviceIdPage() {
  const { caseId, workspace, refresh } = useCaseContext();

  const [deviceId, setDeviceId] = useState("");

  const [report, setReport] = useState<IdentificationReport | null>(null);

  const [scanning, setScanning] = useState(false);

  const [hexOffset, setHexOffset] = useState(0);
  const [structure, setStructure] = useState<StructureNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<StructureNode | null>(null);

  const evidence = workspace?.evidence ?? [];

  useEffect(() => {
    if (evidence[0] && !deviceId) {
      setDeviceId(evidence[0].id);

      setReport(evidence[0].identification ?? null);
    }
  }, [evidence, deviceId]);

  useEffect(() => {
    if (!deviceId) {
      setStructure([]);
      return;
    }
    void api
      .deviceStructure(deviceId)
      .then((result) => {
        setStructure(result.nodes as StructureNode[]);
        setSelectedNode((result.nodes[0] ?? null) as StructureNode | null);
      })
      .catch(() => setStructure([]));
  }, [deviceId]);

  async function runIdentify() {
    if (!deviceId) return;

    setScanning(true);

    try {
      const result = await api.identify(deviceId);

      setReport(result);

      toast.success(`Adapter: ${result.recommended_adapter}`);

      await refresh();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Identification failed",
        { duration: Infinity },
      );
    } finally {
      setScanning(false);
    }
  }

  const flatStructure = useMemo(() => flattenNodes(structure), [structure]);

  const topHit = report?.hits[0];

  const selectedEvidence = evidence.find((e) => e.id === deviceId);

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        kicker="Step 2 · Identification"
        title="Device & format analysis"
        subtitle="Signature scan and partition layout — selects the recovery adapter. Routing hints only until field-validated."
        actions={
          <Button
            disabled={!deviceId || scanning}
            onClick={() => void runIdentify()}
          >
            {scanning ? "Scanning…" : "Run identification"}
          </Button>
        }
      />

      {evidence.length === 0 ? (
        <section className="visily-card p-8 text-[13px] text-[var(--text-secondary)]">
          No evidence yet.{" "}
          <Link
            to={`/cases/${caseId}/acquire`}
            className="text-[var(--accent-500)] underline"
          >
            Acquire an image
          </Link>{" "}
          first.
        </section>
      ) : (
        <div className="grid min-h-[420px] gap-3 lg:grid-cols-[240px_1fr]">
          <section className="visily-card flex flex-col p-3">
            <p className="visily-card-title mb-2 text-[11px]">
              Evidence in this case
            </p>

            <ul className="space-y-1">
              {evidence.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"

                    className={`w-full rounded-lg px-2 py-2 text-left ${
                      deviceId === e.id
                        ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent-500)]/30"
                        : "hover:bg-[var(--surface-3)]"
                    }`}

                    onClick={() => {
                      setDeviceId(e.id);

                      setReport(e.identification ?? null);

                      setHexOffset(0);
                    }}
                  >
                    <p className="truncate text-[12px] font-medium">
                      {e.filename}
                    </p>

                    <p className="mono mt-0.5 text-[10px] text-[var(--text-tertiary)]">
                      {formatBytes(e.size_bytes)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>

            {flatStructure.length > 0 ? (
              <>
                <p className="visily-card-title mb-2 mt-4 text-[11px]">
                  Layout tree
                </p>

                <div className="max-h-48 overflow-auto">
                  {flatStructure.map(({ node, depth }) => (
                    <button
                      key={`${node.type}-${node.offset}-${node.label}`}

                      type="button"

                      className={`block w-full truncate rounded px-1 py-0.5 text-left text-[11px] ${
                        selectedNode?.offset === node.offset &&
                        selectedNode?.label === node.label
                          ? "bg-[var(--accent-soft)] text-[var(--accent-600)]"
                          : "hover:bg-[var(--surface-3)]"
                      }`}

                      style={{ paddingLeft: `${depth * 10 + 4}px` }}

                      onClick={() => {
                        setSelectedNode(node);

                        setHexOffset(node.offset);
                      }}
                    >
                      {node.label}
                    </button>
                  ))}
                </div>
              </>
            ) : null}
          </section>

          <div className="flex min-h-0 flex-col gap-3">
            <section className="visily-card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="visily-card-title text-[11px]">
                    Identification result
                  </p>

                  {selectedEvidence ? (
                    <p className="mt-1 text-[14px] font-semibold text-[var(--text-primary)]">
                      {selectedEvidence.filename}
                    </p>
                  ) : null}
                </div>

                {report?.recommended_adapter ? (
                  <span className="rounded-md bg-[var(--accent-soft)] px-3 py-1 font-mono text-[12px] font-semibold text-[var(--accent-700)]">
                    {report.recommended_adapter}
                  </span>
                ) : null}
              </div>

              {!report ? (
                <p className="mt-4 text-[13px] text-[var(--text-tertiary)]">
                  Run identification to see vendor hits and adapter routing.
                </p>
              ) : (
                <ul className="mt-4 space-y-2">
                  {report.hits.map((hit) => (
                    <li
                      key={`${hit.vendor}-${hit.adapter}`}
                      className="rounded-lg border border-[var(--border-subtle)] px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-[13px] font-semibold text-[var(--text-primary)]">
                            {hit.vendor}
                          </p>

                          <p className="font-mono text-[11px] text-[var(--text-tertiary)]">
                            {hit.adapter}
                          </p>
                        </div>

                        <ConfidenceBadge
                          tier={
                            hit.confidence >= 0.8
                              ? "high"
                              : hit.confidence >= 0.5
                                ? "medium"
                                : "low"
                          }
                        />
                      </div>

                      {hit.markers.length > 0 ? (
                        <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                          Markers: {hit.markers.join(", ")}
                        </p>
                      ) : null}

                      {hit.capability_tier ? (
                        <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-[var(--accent-600)]">
                          {capabilityTierLabel(hit.capability_tier)}
                        </p>
                      ) : null}

                      {hit.validation_scope ? (
                        <p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">
                          {validationScopeLabel(hit.validation_scope)}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}

              {report?.oem_capabilities &&
              report.oem_capabilities.length > 0 ? (
                <div
                  className="mt-4 border-t pt-3"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
                    Coverage across all {report.oem_capabilities.length} vendors
                    named in the problem statement
                  </p>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="text-left text-[10px] uppercase text-[var(--text-tertiary)]">
                          <th className="pb-1 pr-3 font-medium">Vendor</th>
                          <th className="pb-1 pr-3 font-medium">Tier</th>
                          <th className="pb-1 font-medium">Scope</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.oem_capabilities.map((cap) => (
                          <tr
                            key={cap.vendor}
                            className="border-t"
                            style={{ borderColor: "var(--border-subtle)" }}
                          >
                            <td className="py-1 pr-3 font-medium text-[var(--text-primary)]">
                              {cap.vendor}
                            </td>
                            <td className="py-1 pr-3 text-[var(--text-secondary)]">
                              {capabilityTierLabel(cap.capability_tier)}
                            </td>
                            <td className="py-1 text-[var(--text-tertiary)]">
                              {validationScopeLabel(cap.validation_scope)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {report && topHit ? (
                <Button asChild className="mt-4" variant="secondary">
                  <Link to={`/cases/${caseId}/recover`}>
                    Continue to recovery →
                  </Link>
                </Button>
              ) : null}
            </section>

            <section className="visily-card flex min-h-0 flex-1 flex-col p-4">
              {deviceId ? (
                <HexViewer
                  deviceId={deviceId}
                  baseOffset={selectedNode?.offset ?? hexOffset}
                  title={`Hex at ${formatOffset(selectedNode?.offset ?? hexOffset)}`}
                />
              ) : (
                <p className="text-[13px] text-[var(--text-tertiary)]">
                  Select evidence to preview bytes.
                </p>
              )}

              {report?.filesystem_hints &&
              report.filesystem_hints.length > 0 ? (
                <div
                  className="mt-3 border-t pt-3"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <p className="text-[10px] font-bold uppercase text-[var(--text-tertiary)]">
                    Filesystem hints
                  </p>

                  <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                    {report.filesystem_hints.map((h) => (
                      <li key={h.marker}>{h.label}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {report?.coverage_note ? (
                <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">
                  {report.coverage_note}
                </p>
              ) : null}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
