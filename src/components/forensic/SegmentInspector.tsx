import { useEffect, useMemo, useState } from "react";
import {
  api,
  type AiFinding,
  type CustodyLogEntry,
  type Segment,
  type SegmentDetail,
} from "@/lib/api";
import { formatBytes, formatOffset } from "@/lib/utils";
import { formatTimestampSource } from "@/lib/integrity";
import { HexViewer } from "@/components/forensic/HexViewer";

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
  const [tab, setTab] = useState(variant === "recover" ? "hex" : "meta");
  const [detail, setDetail] = useState<SegmentDetail | null>(null);
  const [findings, setFindings] = useState<AiFinding[]>([]);
  const [custody, setCustody] = useState<CustodyLogEntry[]>([]);

  useEffect(() => {
    setTab(variant === "recover" ? "hex" : "meta");
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
      ? (["hex", "provenance"] as const)
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
      ["Container frames", segment?.frame_count ?? detail?.frame_count ?? "—"],
      [
        "Playable frames",
        segment?.playable_frame_count != null
          ? String(segment.playable_frame_count)
          : "— (export to measure)",
      ],
    ],
    [segment, detail],
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
        {tab === "hex" ? (
          <HexViewer
            deviceId={deviceId}
            baseOffset={byteStart}
            pageSize={512}
          />
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
              <div className="space-y-1 text-[11px]">
                <p className="font-semibold uppercase text-[var(--text-tertiary)]">
                  Artifact hashes
                </p>
                {detail.output_md5 ? (
                  <p className="mono break-all">MD5 {detail.output_md5}</p>
                ) : null}
                {detail.output_sha256 ? (
                  <p className="mono break-all">
                    SHA-256 {detail.output_sha256}
                  </p>
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
