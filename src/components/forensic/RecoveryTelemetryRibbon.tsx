import { useMemo } from "react";
import type { EvidenceRecord, Segment } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import {
  countAllocations,
  countInvalidChannels,
  countPartial,
  countPlausibleChannels,
  reportsRecoveryStatus,
} from "@/lib/allocation";

/**
 * Live readout strip for the current evidence image.
 *
 * Every figure here is read straight off the parser's output or the evidence
 * record. There is deliberately no "integrity %", no "read speed", no aggregate
 * confidence score: this engine does not measure those, and a plausible-looking
 * number the tool cannot defend is worse than no number at all.
 *
 * A field with nothing behind it renders as "—" rather than being hidden, so the
 * absence is visible instead of silently papered over.
 */

function Stat({
  label,
  value,
  accent = false,
  title,
}: {
  label: string;
  value: string;
  accent?: boolean;
  title?: string;
}) {
  return (
    <span className="flex items-baseline gap-1.5" title={title}>
      <span className="text-[var(--text-tertiary)]">{label}</span>
      <strong
        className={
          accent
            ? "font-semibold text-[var(--accent-600)]"
            : "font-semibold text-[var(--text-primary)]"
        }
      >
        {value}
      </strong>
    </span>
  );
}

function Divider() {
  return <span className="text-[var(--border-default)]">│</span>;
}

export function RecoveryTelemetryRibbon({
  segments,
  evidence,
  adapter,
}: {
  segments: Segment[];
  evidence: EvidenceRecord | null;
  adapter: string;
}) {
  const counts = useMemo(() => countAllocations(segments), [segments]);

  // Only channels the recorder could actually have written are counted: a byte
  // holding the format's erase pattern is not a camera, and letting it inflate
  // this figure would claim a source that never existed. The recording itself is
  // still listed in the table, flagged as invalid.
  const channels = useMemo(() => countPlausibleChannels(segments), [segments]);
  const invalidChannels = useMemo(
    () => countInvalidChannels(segments),
    [segments],
  );
  const partial = useMemo(() => countPartial(segments), [segments]);
  // Parsers that never assess completeness must not read as "checked, all whole".
  const assessesPartial = useMemo(
    () => reportsRecoveryStatus(segments),
    [segments],
  );

  const recoveredBytes = useMemo(
    () =>
      segments.reduce(
        (total, s) =>
          total +
          (s.byte_length ?? (s.offset_end ?? 0) - (s.offset_start ?? 0)),
        0,
      ),
    [segments],
  );

  // Device identity the parser actually read out of the master sector.
  const firmware = useMemo(() => {
    for (const segment of segments) {
      const value = segment.signature_evidence?.["firmware"];
      if (typeof value === "string" && value) return value;
    }
    return null;
  }, [segments]);

  const imageSize = evidence?.size_bytes ?? 0;

  return (
    <div className="rec-ribbon flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-4 py-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <Stat
          label="Recordings"
          value={String(segments.length)}
          accent={segments.length > 0}
        />
        <Divider />
        <Stat
          label="Deleted"
          value={String(counts.deleted)}
          accent={counts.deleted > 0}
          title="Recordings recovered from a cleared index entry"
        />
        <Divider />
        <Stat
          label="Partial"
          value={assessesPartial ? String(partial) : "—"}
          accent={partial > 0}
          title={
            assessesPartial
              ? "Recordings whose data block was partly overwritten — only the bytes inside the entry's own window are reported as recovered"
              : "This parser does not assess whether a recording's bytes are all still present, so no completeness claim is made either way"
          }
        />
        <Divider />
        <Stat
          label="Channels"
          value={channels ? String(channels) : "—"}
          title={
            invalidChannels > 0
              ? `${invalidChannels} recording(s) carry a channel byte that cannot name a camera and are excluded from this count`
              : "Distinct cameras across the recovered recordings"
          }
        />
        {invalidChannels > 0 ? (
          <>
            <Divider />
            <Stat
              label="Invalid ch"
              value={String(invalidChannels)}
              accent
              title="Channel byte is 0x00 or 0xFF (the format's erase pattern); the raw value is preserved on the row"
            />
          </>
        ) : null}
        <Divider />
        <Stat
          label="Carved"
          value={recoveredBytes ? formatBytes(recoveredBytes) : "—"}
          title="Total bytes across every recovered extent"
        />
        <Divider />
        <Stat label="Image" value={imageSize ? formatBytes(imageSize) : "—"} />
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10.5px]">
        <span className="text-[var(--text-tertiary)]">
          PARSER{" "}
          <span className="font-semibold text-[var(--text-secondary)]">
            {adapter || "—"}
          </span>
        </span>
        <Divider />
        <span
          className="text-[var(--text-tertiary)]"
          title="Firmware string read from the recorder's master sector"
        >
          FIRMWARE{" "}
          <span className="font-semibold text-[var(--text-secondary)]">
            {firmware ?? "—"}
          </span>
        </span>
        <Divider />
        <span className="text-[var(--text-tertiary)]">
          MEDIA{" "}
          <span className="font-semibold text-[var(--text-secondary)]">
            {evidence?.media_type ?? "—"}
          </span>
        </span>
      </div>
    </div>
  );
}
