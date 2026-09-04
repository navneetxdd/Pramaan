import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  api,
  type AiFinding,
  type CustodyLogEntry,
  type Segment,
  type SegmentDetail,
} from "@/lib/api";
import { formatBytes, formatOffset } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";
import { allocationLabel, allocationOf } from "@/lib/allocation";
import { HexViewer } from "@/components/forensic/HexViewer";
import { Button } from "@/components/ui/button";
import { getApiBase } from "@/lib/apiBase";

type ExportResult = { filename: string; download_url: string };

/**
 * Export affordance for a recovered recording.
 *
 * Calls POST /devices/{id}/sequences/{segment_id}/export, which unwraps the
 * carved bytes and remuxes to MP4 when FFmpeg is present, falling back to raw
 * H.264 when it is not. The pipeline behind it is still being completed
 * (Hikvision picture-index stripping and playable_frame_count) — see
 * docs/reference/hikvision_playback_handoff.md — so this reports exactly what
 * came back rather than promising a playable MP4.
 */
function ExportSegmentButton({
  deviceId,
  segmentId,
}: {
  deviceId: string;
  segmentId: string;
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);

  useEffect(() => {
    setResult(null);
  }, [segmentId]);

  async function run() {
    setBusy(true);
    try {
      const response = (await api.exportSegment(deviceId, segmentId, {
        full: true,
      })) as ExportResult;
      setResult(response);
      toast.success(`Exported ${response.filename}`);
    } catch (err) {
      // 409 here means the artifact failed its byte-length/identity check —
      // surface it verbatim rather than as a generic failure.
      toast.error(err instanceof Error ? err.message : "Export failed", {
        duration: Infinity,
      });
    } finally {
      setBusy(false);
    }
  }

  const isMp4 = result?.filename.toLowerCase().endsWith(".mp4");

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase text-[var(--text-tertiary)]">
        Export
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() => void run()}
        >
          {busy ? "Exporting…" : "Export segment"}
        </Button>
        {result ? (
          <a
            href={`${getApiBase()}${result.download_url}`}
            download={result.filename}
            className="mono text-[11px] text-[var(--accent-500)] underline underline-offset-2"
          >
            {result.filename}
          </a>
        ) : null}
      </div>
      {result && !isMp4 ? (
        <p className="text-[10px] text-[var(--status-warning)]">
          Exported as raw H.264 — FFmpeg was not available, so this is not a
          container-wrapped, directly playable file.
        </p>
      ) : null}
    </div>
  );
}

/** Read one key out of a parser's validation_evidence bag. */
function evidenceValue(
  segment: Segment | null,
  detail: SegmentDetail | null,
  key: string,
): unknown {
  return (
    segment?.validation_evidence?.[key] ?? detail?.validation_evidence?.[key]
  );
}

function displayOrDash(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

/**
 * Frame rate as the engine measured it. `String(6.0)` is "6", which reads like
 * an integer guess rather than a decoded VUI value, so keep one decimal — but
 * never pad a rate that genuinely has more precision (e.g. 29.97).
 */
function formatFps(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return displayOrDash(value);
  }
  const text = Number.isInteger(value) ? value.toFixed(1) : String(value);
  return `${text} fps`;
}

async function copyText(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success(`${label} copied`);
  } catch {
    toast.error("Could not copy to clipboard");
  }
}

/** Hash row with a copy button. Long digests wrap rather than truncate. */
function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="w-16 shrink-0 pt-0.5 text-[10px] uppercase text-[var(--text-tertiary)]">
        {label}
      </span>
      <span className="mono min-w-0 flex-1 break-all text-[11px] text-[var(--text-secondary)]">
        {value}
      </span>
      <button
        type="button"
        onClick={() => void copyText(value, label)}
        title={`Copy ${label}`}
        aria-label={`Copy ${label}`}
        className="shrink-0 rounded border border-[var(--border-default)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)] hover:bg-[var(--surface-3)]"
      >
        Copy
      </button>
    </div>
  );
}

type SegmentInspectorProps = {
  caseId: string;
  deviceId: string;
  segment: Segment | null;
  variant?: "timeline" | "recover";
};

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-40 overflow-auto rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] p-2 font-mono text-[10px] text-[var(--text-secondary)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function SegmentInspector({
  caseId,
  deviceId,
  segment,
  variant = "timeline",
}: SegmentInspectorProps) {
  const [tab, setTab] = useState(variant === "recover" ? "metadata" : "meta");
  const [detail, setDetail] = useState<SegmentDetail | null>(null);
  const [findings, setFindings] = useState<AiFinding[]>([]);
  const [custody, setCustody] = useState<CustodyLogEntry[]>([]);

  useEffect(() => {
    setTab(variant === "recover" ? "metadata" : "meta");
  }, [segment?.id, variant]);

  useEffect(() => {
    if (!segment?.id || !deviceId) {
      setDetail(null);
      setFindings([]);
      setCustody([]);
      return;
    }
    void api
      .getSegmentDetail(deviceId, segment.id)
      .then(setDetail)
      .catch(() => setDetail(null));
    void api
      .listAiFindings(deviceId)
      .then((r) =>
        setFindings(r.findings.filter((f) => f.sequence_id === segment.id)),
      )
      .catch(() => setFindings([]));
  }, [deviceId, segment?.id]);

  useEffect(() => {
    const digest = detail?.output_sha256;
    if (!digest) {
      setCustody([]);
      return;
    }
    void api
      .custodyLogByDigest(caseId, digest)
      .then(setCustody)
      .catch(() => setCustody([]));
  }, [caseId, detail?.output_sha256]);

  const tabs =
    variant === "recover"
      ? (["metadata", "hex", "provenance"] as const)
      : (["meta", "findings", "validation"] as const);

  const byteStart = segment?.offset_start ?? detail?.byte_start ?? 0;

  const metaRows = useMemo(
    () => [
      ["Channel", segment?.channel ?? detail?.channel ?? "—"],
      [
        "Byte range",
        segment
          ? `${formatOffset(segment.offset_start)}–${formatOffset(segment.offset_end)}`
          : "—",
      ],
      ["Size", formatBytes(segment?.byte_length ?? detail?.byte_length ?? 0)],
      [
        "Parser",
        `${detail?.parser_name ?? segment?.parser_name ?? "—"} ${detail?.parser_version ?? segment?.parser_version ?? ""}`.trim(),
      ],
      ["Validation", segment?.validation ?? detail?.validation_level ?? "—"],
      [
        "Recorder start",
        segment?.recorder_start_ts ?? detail?.recorder_start_ts ?? "—",
      ],
      [
        "Corrected start",
        segment?.corrected_start_ts ?? detail?.corrected_start_ts ?? "—",
      ],
      [
        "Timestamp source",
        formatTimestampSource(
          segment?.timestamp_source ?? detail?.timestamp_source,
        ),
      ],
      [
        "Confidence",
        segment?.timestamp_confidence ?? detail?.timestamp_confidence ?? "—",
      ],
      ["Recovery job", detail?.recovery_job_id ?? segment?.job_id ?? "—"],
      [
        "Container units",
        segment?.container_units ?? detail?.frame_count ?? "—",
      ],
      [
        "Playable frames",
        segment?.playable_frame_count != null
          ? String(segment.playable_frame_count)
          : "— (export to measure)",
      ],
    ],
    [segment, detail],
  );

  /**
   * Recording telemetry the parsers extracted from the stream itself —
   * resolution and fps from the H.264 SPS/VUI, event type from the IDR table
   * cadence. Absent values render as "—"; nothing here is defaulted or guessed.
   */
  const forensicRows = useMemo(() => {
    if (!segment) return [];
    return [
      ["Channel", displayOrDash(segment.channel ?? detail?.channel)],
      ["Allocation state", allocationLabel(allocationOf(segment))],
      [
        "Event type",
        displayOrDash(evidenceValue(segment, detail, "event_type")),
      ],
      [
        "Resolution",
        displayOrDash(evidenceValue(segment, detail, "resolution")),
      ],
      ["Frame rate", formatFps(evidenceValue(segment, detail, "fps"))],
      ["Codec", displayOrDash(segment.codec ?? detail?.codec)],
      [
        "Recorder start",
        displayOrDash(segment.recorder_start_ts ?? detail?.recorder_start_ts),
      ],
      [
        "Recorder end",
        displayOrDash(segment.recorder_end_ts ?? detail?.recorder_end_ts),
      ],
      [
        "Timestamp source",
        formatTimestampSource(
          segment.timestamp_source ?? detail?.timestamp_source,
        ),
      ],
      [
        "Timestamp confidence",
        displayOrDash(
          segment.timestamp_confidence ?? detail?.timestamp_confidence,
        ),
      ],
      [
        "Byte range",
        `${formatOffset(segment.offset_start)}–${formatOffset(segment.offset_end)}`,
      ],
      ["Size", formatBytes(segment.byte_length ?? detail?.byte_length ?? 0)],
    ] as Array<[string, string]>;
  }, [segment, detail]);

  const confidenceBasis = evidenceValue(
    segment,
    detail,
    "timestamp_confidence_basis",
  );

  if (!segment) {
    return (
      <section className="visily-card flex min-h-[200px] items-center justify-center p-4 text-[13px] text-[var(--text-tertiary)]">
        Select a segment to inspect metadata, findings, and hex.
      </section>
    );
  }

  return (
    <section className="visily-card flex min-h-[280px] flex-col overflow-hidden">
      <div className="visily-card-header">
        <span className="visily-card-title">Segment inspector</span>
        <span className="mono text-[10px] text-[var(--text-tertiary)]">
          {segment.id.slice(0, 8)}…
        </span>
      </div>
      <div className="flex gap-1 border-b border-[var(--border-subtle)] px-3 pt-2">
        {tabs.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={
              tab === name
                ? "border-b-2 border-[var(--accent-500)] px-2 pb-2 text-[11px] font-semibold uppercase text-[var(--accent-500)]"
                : "px-2 pb-2 text-[11px] uppercase text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
            }
          >
            {name}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {tab === "metadata" ? (
          <div className="space-y-3">
            <table className="w-full text-[12px]">
              <tbody>
                {forensicRows.map(([label, value]) => (
                  <tr
                    key={label}
                    className="border-b border-[var(--border-subtle)]"
                  >
                    <td className="py-1.5 pr-3 text-[var(--text-tertiary)]">
                      {label}
                    </td>
                    <td className="mono py-1.5 text-[var(--text-primary)]">
                      {value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {typeof confidenceBasis === "string" && confidenceBasis ? (
              <div className="rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] p-2">
                <p className="mb-1 text-[10px] font-semibold uppercase text-[var(--text-tertiary)]">
                  Why this confidence
                </p>
                <p className="text-[11px] leading-relaxed text-[var(--text-secondary)]">
                  {confidenceBasis}
                </p>
              </div>
            ) : null}

            {detail?.output_md5 || detail?.output_sha256 ? (
              <div className="space-y-1.5">
                <p className="text-[10px] font-semibold uppercase text-[var(--text-tertiary)]">
                  Artifact hashes
                </p>
                {detail.output_md5 ? (
                  <CopyRow label="MD5" value={detail.output_md5} />
                ) : null}
                {detail.output_sha256 ? (
                  <CopyRow label="SHA-256" value={detail.output_sha256} />
                ) : null}
              </div>
            ) : null}
            <ExportSegmentButton deviceId={deviceId} segmentId={segment.id} />
          </div>
        ) : null}
        {tab === "hex" ? (
          // rec-hex scopes the dark buffer treatment to the Recovery inspector;
          // the Identification page uses the same viewer and is untouched.
          <div className={variant === "recover" ? "rec-hex" : undefined}>
            <HexViewer
              deviceId={deviceId}
              baseOffset={byteStart}
              pageSize={512}
            />
          </div>
        ) : null}
        {tab === "meta" || tab === "provenance" ? (
          <div className="space-y-3">
            <table className="w-full text-[12px]">
              <tbody>
                {metaRows.map(([label, value]) => (
                  <tr
                    key={label}
                    className="border-b border-[var(--border-subtle)]"
                  >
                    <td className="py-1.5 pr-3 text-[var(--text-tertiary)]">
                      {label}
                    </td>
                    <td className="mono py-1.5 text-[var(--text-primary)]">
                      {String(value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {detail?.output_md5 || detail?.output_sha256 ? (
              <div className="space-y-1.5">
                <p className="text-[10px] font-semibold uppercase text-[var(--text-tertiary)]">
                  Artifact hashes
                </p>
                {detail.output_md5 ? (
                  <CopyRow label="MD5" value={detail.output_md5} />
                ) : null}
                {detail.output_sha256 ? (
                  <CopyRow label="SHA-256" value={detail.output_sha256} />
                ) : null}
              </div>
            ) : null}
            {tab === "provenance" && custody.length > 0 ? (
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase text-[var(--text-tertiary)]">
                  Custody (digest match)
                </p>
                <ul className="space-y-1 text-[11px]">
                  {custody.map((row) => (
                    <li
                      key={row.id}
                      className="rounded border border-[var(--border-subtle)] px-2 py-1"
                    >
                      <span className="mono">{row.timestamp_utc}</span> ·{" "}
                      {row.action} · {row.actor}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {tab === "provenance" ? (
              <>
                <p className="text-[11px] font-semibold uppercase text-[var(--text-tertiary)]">
                  Signature evidence
                </p>
                <JsonBlock
                  value={
                    detail?.signature_evidence ??
                    segment.signature_evidence ??
                    {}
                  }
                />
              </>
            ) : null}
          </div>
        ) : null}
        {tab === "findings" ? (
          findings.length === 0 ? (
            <p className="text-[13px] text-[var(--text-tertiary)]">
              No AI findings for this segment.
            </p>
          ) : (
            <ul className="space-y-2">
              {findings.map((f) => (
                <li
                  key={f.id}
                  className="rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] px-2 py-1.5 text-[12px]"
                >
                  <span className="font-medium">{f.finding_type}</span>
                  {f.label ? ` · ${f.label}` : ""}
                  <span className="mono ml-2 text-[10px] text-[var(--text-tertiary)]">
                    @ {f.frame_offset_ms}ms · conf {f.confidence ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )
        ) : null}
        {tab === "validation" ? (
          <JsonBlock
            value={
              detail?.validation_evidence ?? segment.validation_evidence ?? {}
            }
          />
        ) : null}
      </div>
    </section>
  );
}
