import { X } from "lucide-react";
import type { EvidenceRecord } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import {
  categoryLabel,
  categoryOf,
  verificationStatusLabel,
  verificationStatusOf,
  verificationStatusTone,
} from "@/lib/evidenceCatalog";

type EvidenceComparisonBarProps = {
  items: EvidenceRecord[];
  onRemove: (id: string) => void;
  onClear: () => void;
};

/**
 * Side-by-side comparison of selected rows.
 *
 * Purely a re-presentation of data the catalog already fetched — no request, no
 * derivation the table does not already make. The full 64-hex digest is shown
 * rather than a short form, because the reason to put two items next to each
 * other is usually to read their hashes against one another; a truncated digest
 * cannot settle that.
 */
export function EvidenceComparisonBar({
  items,
  onRemove,
  onClear,
}: EvidenceComparisonBarProps) {
  if (items.length < 2) return null;

  const digests = items.map((item) => (item.sha256 ?? "").toLowerCase());
  const allDigestsPresent = digests.every((digest) => digest.length > 0);
  const identical =
    allDigestsPresent && new Set(digests).size === 1 && digests.length > 1;

  return (
    <section
      className="visily-card shrink-0"
      aria-label={`Comparing ${items.length} evidence items`}
    >
      <div className="visily-card-header">
        <span className="visily-card-title">
          Comparing {items.length} items
        </span>
        <div className="flex items-center gap-3">
          {allDigestsPresent ? (
            <span
              className="mono text-[10px] font-bold uppercase tracking-wide"
              style={{
                color: identical
                  ? "var(--status-warning)"
                  : "var(--text-tertiary)",
              }}
            >
              {identical
                ? "SHA-256 identical across selection"
                : "SHA-256 differs across selection"}
            </span>
          ) : (
            <span className="mono text-[10px] uppercase text-[var(--text-tertiary)]">
              Selection includes an item with no stored hash
            </span>
          )}
          <button
            type="button"
            className="text-[10px] font-semibold uppercase text-[var(--accent-500)] hover:underline"
            onClick={onClear}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div
          className="grid min-w-full gap-px p-px"
          style={{
            gridTemplateColumns: `repeat(${items.length}, minmax(240px, 1fr))`,
            background: "var(--border-subtle)",
          }}
        >
          {items.map((item) => {
            const status = verificationStatusOf(item);
            const tone = verificationStatusTone(status);
            return (
              <div
                key={item.id}
                className="p-3"
                style={{ background: "var(--surface-2)" }}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="break-all text-[12px] font-semibold text-[var(--text-primary)]">
                    {item.filename}
                  </p>
                  <button
                    type="button"
                    className="shrink-0 rounded p-0.5 text-[var(--text-tertiary)] hover:bg-[var(--surface-4)] hover:text-[var(--text-primary)]"
                    onClick={() => onRemove(item.id)}
                    aria-label={`Remove ${item.filename} from comparison`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>

                <dl className="mt-2 space-y-1.5 text-[11px]">
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--text-tertiary)]">Size</dt>
                    <dd className="mono text-[var(--text-primary)]">
                      {formatBytes(item.size_bytes)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--text-tertiary)]">Category</dt>
                    <dd className="text-[var(--text-primary)]">
                      {categoryLabel(categoryOf(item))}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-[var(--text-tertiary)]">
                      Verification
                    </dt>
                    <dd
                      className="font-medium"
                      style={{
                        color:
                          tone === "danger"
                            ? "var(--status-danger)"
                            : tone === "warning"
                              ? "var(--status-warning)"
                              : tone === "success"
                                ? "var(--status-success)"
                                : "var(--text-primary)",
                      }}
                    >
                      {verificationStatusLabel(status)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[var(--text-tertiary)]">SHA-256</dt>
                    <dd className="mono mt-0.5 break-all text-[10px] leading-relaxed text-[var(--text-secondary)]">
                      {item.sha256 || "No hash on record"}
                    </dd>
                  </div>
                </dl>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
