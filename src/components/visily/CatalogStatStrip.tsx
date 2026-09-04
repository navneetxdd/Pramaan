import { AlertTriangle, Clock, Database, FileStack } from "lucide-react";
import { formatBytes } from "@/lib/utils";

type CatalogStatStripProps = {
  storageBytes: number;
  artefactCount: number;
  processingJobs: number;
  auditErrors: number;
};

export function CatalogStatStrip({
  storageBytes,
  artefactCount,
  processingJobs,
  auditErrors,
}: CatalogStatStripProps) {
  const stats = [
    {
      label: "Storage load",
      value: formatBytes(storageBytes),
      icon: Database,
      tone: "info" as const,
    },
    {
      label: "Artefact count",
      value: artefactCount.toLocaleString(),
      icon: FileStack,
      tone: "neutral" as const,
    },
    {
      label: "Processing jobs",
      value: String(processingJobs),
      icon: Clock,
      tone: "neutral" as const,
    },
    {
      label: "Failed jobs",
      value: String(auditErrors),
      icon: AlertTriangle,
      tone: auditErrors > 0 ? ("danger" as const) : ("success" as const),
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="visily-catalog-stat">
          <div>
            <p className="text-[20px] font-semibold leading-none text-[var(--text-primary)]">
              {s.value}
            </p>
            <p className="mt-1 text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
              {s.label}
            </p>
          </div>
          <s.icon
            className="h-5 w-5"
            style={{
              color:
                s.tone === "danger"
                  ? "var(--status-danger)"
                  : s.tone === "success"
                    ? "var(--status-success)"
                    : s.tone === "info"
                      ? "var(--accent-500)"
                      : "var(--text-tertiary)",
            }}
            strokeWidth={1.5}
          />
        </div>
      ))}
    </div>
  );
}
