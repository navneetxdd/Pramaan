import { HardDrive, Clock, MapPin } from "lucide-react";
import type { CustodyEvent, EvidenceRecord } from "@/lib/api";
import { formatBytes, shortHash } from "@/lib/utils";

type EvidenceInspectorProps = {
  item: EvidenceRecord | null;
  custodyEvents: CustodyEvent[];
};

export function EvidenceInspector({
  item,
  custodyEvents,
}: EvidenceInspectorProps) {
  if (!item) {
    return (
      <aside className="visily-inspector">
        <div className="visily-inspector-header">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
            Evidence inspector
          </span>
        </div>
        <p className="p-6 text-[13px] text-[var(--text-tertiary)]">
          Select an evidence item to inspect provenance and custody.
        </p>
      </aside>
    );
  }

  const related = custodyEvents
    .filter((e) => !e.image_id || e.image_id === item.id)
    .slice(-4)
    .reverse();
  const oem = item.identification?.recommended_adapter;

  return (
    <aside className="visily-inspector">
      <div className="visily-inspector-header">
        <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          Evidence inspector
        </span>
      </div>

      <div className="visily-inspector-preview">
        <HardDrive
          className="h-16 w-16 text-[var(--accent-400)]"
          strokeWidth={1}
        />
      </div>

      <div className="space-y-4 p-4">
        <div>
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">
            {item.filename}
          </h3>
          <p className="mono mt-1 text-[10px] text-[var(--text-tertiary)]">
            {item.id}
          </p>
        </div>

        <dl className="space-y-2 text-[12px]">
          <div
            className="flex justify-between gap-2 border-b pb-2"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <dt className="text-[var(--text-tertiary)]">Size</dt>
            <dd className="mono font-medium text-[var(--text-primary)]">
              {formatBytes(item.size_bytes)}
            </dd>
          </div>
          <div
            className="flex justify-between gap-2 border-b pb-2"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <dt className="text-[var(--text-tertiary)]">Media type</dt>
            <dd className="font-medium capitalize text-[var(--text-primary)]">
              {item.media_type || "disk image"}
            </dd>
          </div>
          {oem ? (
            <div
              className="flex justify-between gap-2 border-b pb-2"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <dt className="text-[var(--text-tertiary)]">Adapter</dt>
              <dd className="mono text-[11px] text-[var(--text-primary)]">
                {oem}
              </dd>
            </div>
          ) : null}
          <div
            className="flex justify-between gap-2 border-b pb-2"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <dt className="text-[var(--text-tertiary)]">Status</dt>
            <dd>
              <span className="visily-badge visily-badge-success text-[9px]">
                {item.acquisition_status === "complete"
                  ? "Verified"
                  : (item.acquisition_status ?? "acquired")}
              </span>
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="text-[var(--text-tertiary)]">SHA-256</dt>
            <dd className="mono text-[10px] text-[var(--text-secondary)]">
              {shortHash(item.sha256)}
            </dd>
          </div>
        </dl>

        <div>
          <div className="mb-2 flex items-center gap-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
              Custody timeline
            </p>
            <Clock className="h-3 w-3 text-[var(--accent-500)]" />
          </div>
          <ul className="space-y-3">
            {related.length === 0 ? (
              <li className="text-[12px] text-[var(--text-tertiary)]">
                No custody events for this item yet.
              </li>
            ) : (
              related.map((ev) => (
                <li
                  key={ev.id}
                  className="border-l-2 pl-3"
                  style={{ borderColor: "var(--accent-400)" }}
                >
                  <p className="text-[12px] font-medium text-[var(--text-primary)]">
                    {ev.action}
                  </p>
                  <p className="mono mt-0.5 text-[10px] text-[var(--text-tertiary)]">
                    {ev.created_at.replace("T", " ").slice(0, 16)} · {ev.actor}
                  </p>
                  {ev.detail ? (
                    <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                      {ev.detail}
                    </p>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </aside>
  );
}
