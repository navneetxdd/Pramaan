import { Link } from "react-router-dom";
import { HardDrive, Cpu, Network, Cloud, MemoryStick } from "lucide-react";
import { formatBytes, shortHash } from "@/lib/utils";

type EvidenceTileProps = {
  id: string;
  caseId: string;
  label: string;
  sizeBytes: number;
  sha256: string;
  kind?: "disk" | "mobile" | "network" | "cloud" | "memory";
  status?: string;
};

const icons = {
  disk: HardDrive,
  mobile: Cpu,
  network: Network,
  cloud: Cloud,
  memory: MemoryStick,
};

export function EvidenceTile({ id, caseId, label, sizeBytes, sha256, kind = "disk", status }: EvidenceTileProps) {
  const Icon = icons[kind];

  return (
    <Link to={`/cases/${caseId}/evidence`} className="visily-evidence-tile group">
      <div className="visily-evidence-thumb">
        <Icon className="h-8 w-8 text-[var(--accent-400)] opacity-80" strokeWidth={1.25} />
      </div>
      <div className="mt-3 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{label}</p>
          {status ? <span className="visily-badge visily-badge-neutral text-[9px]">{status}</span> : null}
        </div>
        <p className="mono text-[11px] text-[var(--text-tertiary)]">{formatBytes(sizeBytes)}</p>
        <p className="mono text-[10px] text-[var(--text-tertiary)]">SHA {shortHash(sha256)}</p>
      </div>
    </Link>
  );
}
