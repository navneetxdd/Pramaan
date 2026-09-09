import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Clock,
  HardDrive,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, type CustodyEvent, type EvidenceRecord } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { custodyActionLabel, recoveryAdapterLabel } from "@/lib/integrity";
import { countAllocations } from "@/lib/allocation";
import { countSegmentKinds } from "@/lib/caseStats";
import { isNotFound } from "@/lib/apiError";
import {
  acquisitionStatusLabel,
  categoryDescription,
  categoryLabel,
  categoryOf,
  crossCheckHash,
  custodyEventsForItem,
  hashCrossCheckLabel,
  isKnownVerificationStatus,
  mediaTypeLabel,
  verificationStatusLabel,
  verificationStatusOf,
  verificationStatusTone,
  type HashCrossCheck,
} from "@/lib/evidenceCatalog";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

type EvidenceInspectorProps = {
  item: EvidenceRecord | null;
  custodyEvents: CustodyEvent[];
  /** The whole case's evidence, needed to tell a custody gap apart from a
   *  custody contradiction. See `crossCheckHash`. */
  caseEvidence: EvidenceRecord[];
  caseId: string;
  /** True while the case workspace itself is still loading. */
  loading?: boolean;
};

/** Recovery output attributable to one source image. */
type RecoveredFromSource = {
  total: number;
  recordings: number;
  carves: number;
  filesystemUndelete: number;
  deleted: number;
};

const CUSTODY_EVENTS_SHOWN = 4;

export function EvidenceInspector({
  item,
  custodyEvents,
  caseEvidence,
  caseId,
  loading = false,
}: EvidenceInspectorProps) {
  if (loading && !item) return <InspectorLoading />;

  if (!item) {
    return (
      <aside className="visily-inspector">
        <InspectorHeader />
        <p className="p-6 text-[13px] text-[var(--text-tertiary)]">
          Select an evidence item to inspect provenance, integrity and custody.
        </p>
      </aside>
    );
  }

  return (
    <InspectorBody
      item={item}
      custodyEvents={custodyEvents}
      caseEvidence={caseEvidence}
      caseId={caseId}
    />
  );
}

function InspectorHeader() {
  return (
    <div className="visily-inspector-header">
      <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
        Evidence inspector
      </span>
    </div>
  );
}

function InspectorLoading() {
  return (
    <aside className="visily-inspector">
      <InspectorHeader />
      <div className="space-y-4 p-4">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <div className="space-y-2 pt-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-4 w-full" />
          ))}
        </div>
      </div>
      <span className="sr-only">Loading evidence inspector…</span>
    </aside>
  );
}

function InspectorBody({
  item,
  custodyEvents,
  caseEvidence,
  caseId,
}: {
  item: EvidenceRecord;
  custodyEvents: CustodyEvent[];
  caseEvidence: EvidenceRecord[];
  caseId: string;
}) {
  const recovered = useRecoveredFromSource(item.id);

  // Only rows the custody log actually bound to this image's hash. The log is
  // case-scoped, so an unfiltered list would attribute another item's handling
  // to this one.
  const boundEvents = custodyEventsForItem(item, custodyEvents);
  const shown = [...boundEvents].reverse().slice(0, CUSTODY_EVENTS_SHOWN);
  // Cross-check runs over the whole case log, not the hash-bound subset: rows
  // selected by the hash can only ever agree with it.
  const crossCheck = crossCheckHash(item, custodyEvents, caseEvidence);

  const adapter = item.identification?.recommended_adapter;
  const category = categoryOf(item);
  const verification = verificationStatusOf(item);
  const verificationKnown = isKnownVerificationStatus(verification);

  return (
    <aside className="visily-inspector overflow-y-auto">
      <InspectorHeader />

      <div className="visily-inspector-preview">
        <HardDrive
          className="h-16 w-16 text-[var(--accent-400)]"
          strokeWidth={1}
        />
      </div>

      <div className="space-y-4 p-4">
        <div>
          <h3 className="break-all text-[15px] font-semibold text-[var(--text-primary)]">
            {item.filename}
          </h3>
          <p className="mono mt-1 break-all text-[10px] text-[var(--text-tertiary)]">
            {item.id}
          </p>
        </div>

        <HashCrossCheckPanel check={crossCheck} sha256={item.sha256} />

        {!verificationKnown ? (
          <div
            className="rounded-md border p-2.5"
            style={{
              borderColor: "var(--status-danger)",
              background: "rgba(239, 68, 68, 0.08)",
            }}
          >
            <p className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--status-danger)]">
              <AlertTriangle className="h-3.5 w-3.5" />
              Unrecognised verification_status
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
              The engine stored <span className="mono">{verification}</span>,
              which this build does not know how to interpret. Report it — do
              not treat it as verified.
            </p>
          </div>
        ) : null}

        <dl className="space-y-2 text-[12px]">
          <Row label="Size" value={formatBytes(item.size_bytes)} mono />
          <Row
            label="Category"
            value={categoryLabel(category)}
            title={categoryDescription(category)}
            tone={category === "unclassified" ? "danger" : undefined}
          />
          <Row label="Media type" value={mediaTypeLabel(item.media_type)} />
          <Row
            label="Acquisition method"
            value={acquisitionStatusLabel(item.acquisition_method)}
          />
          <Row
            label="Verification"
            value={verificationStatusLabel(verification)}
            tone={verificationStatusTone(verification)}
          />
          <Row
            label="Acquisition state"
            value={acquisitionStatusLabel(item.acquisition_status)}
          />
          {adapter && adapter !== "needs_selection" ? (
            <Row
              label="Recovery method"
              value={recoveryAdapterLabel(adapter)}
            />
          ) : null}
          {item.write_blocker ? (
            <Row
              label="Write blocker"
              value={item.write_blocker.replace(/_/g, " ")}
            />
          ) : null}
          {item.source_identifier ? (
            <Row label="Source" value={item.source_identifier} mono last />
          ) : null}
        </dl>

        <Separator />

        <RecoveredPanel caseId={caseId} recovered={recovered} />

        <Separator />

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                Chain of custody
              </p>
              <Clock className="h-3 w-3 text-[var(--accent-500)]" />
            </div>
            <Link
              to={`/cases/${caseId}/custody?evidence=${encodeURIComponent(item.id)}`}
              className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-[var(--accent-500)] hover:underline"
            >
              Full log
              <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          {boundEvents.length === 0 ? (
            <p className="text-[12px] text-[var(--text-tertiary)]">
              No custody entry is bound to this item&apos;s hash. The custody
              log is recorded per case; open the full log to review every event.
            </p>
          ) : (
            <>
              <p className="mb-2 text-[11px] text-[var(--text-tertiary)]">
                {shown.length} of {boundEvents.length} event
                {boundEvents.length === 1 ? "" : "s"} bound to this item&apos;s
                hash.
              </p>
              <ul className="space-y-3">
                {shown.map((event) => (
                  <li
                    key={event.id}
                    className="border-l-2 pl-3"
                    style={{ borderColor: "var(--accent-400)" }}
                  >
                    <p className="text-[12px] font-medium text-[var(--text-primary)]">
                      {custodyActionLabel(event.action)}
                    </p>
                    <p className="mono mt-0.5 text-[10px] text-[var(--text-tertiary)]">
                      {event.created_at.replace("T", " ").slice(0, 16)} ·{" "}
                      {event.actor}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

function Row({
  label,
  value,
  mono,
  tone,
  title,
  last,
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: "success" | "warning" | "danger" | "neutral";
  title?: string;
  last?: boolean;
}) {
  const color =
    tone === "danger"
      ? "var(--status-danger)"
      : tone === "warning"
        ? "var(--status-warning)"
        : tone === "success"
          ? "var(--status-success)"
          : "var(--text-primary)";
  return (
    <div
      className={
        last
          ? "flex justify-between gap-2"
          : "flex justify-between gap-2 border-b pb-2"
      }
      style={last ? undefined : { borderColor: "var(--border-subtle)" }}
      title={title}
    >
      <dt className="shrink-0 text-[var(--text-tertiary)]">{label}</dt>
      <dd
        className={`text-right font-medium ${mono ? "mono break-all text-[10px]" : "text-[11px]"}`}
        style={{ color }}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * The integrity headline. Two stored values are compared — the catalog record's
 * sha256 and the digest custody recorded for it. Nothing is re-hashed, and the
 * result sits at the top of the panel rather than in a tooltip, because a
 * disagreement between the two books is the finding that invalidates
 * everything below it.
 */
function HashCrossCheckPanel({
  check,
  sha256,
}: {
  check: HashCrossCheck;
  sha256: string;
}) {
  const config = {
    match: {
      icon: ShieldCheck,
      color: "var(--status-success)",
      background: "rgba(34, 197, 94, 0.10)",
    },
    mismatch: {
      icon: ShieldAlert,
      color: "var(--status-danger)",
      background: "rgba(239, 68, 68, 0.10)",
    },
    no_custody_digest: {
      icon: ShieldQuestion,
      color: "var(--text-tertiary)",
      background: "var(--surface-3)",
    },
    no_stored_hash: {
      icon: ShieldQuestion,
      color: "var(--status-warning)",
      background: "rgba(217, 119, 6, 0.10)",
    },
  }[check.state];
  const Icon = config.icon;

  return (
    <div
      className="rounded-md border p-2.5"
      style={{ borderColor: config.color, background: config.background }}
    >
      <p
        className="flex items-center gap-1.5 text-[12px] font-semibold"
        style={{ color: config.color }}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" />
        {hashCrossCheckLabel(check)}
      </p>
      {check.state === "mismatch" ? (
        <div className="mt-2 space-y-1">
          <p className="text-[11px] text-[var(--text-secondary)]">
            The stored record hash and the hash custody recorded for this item
            are not the same value. Do not rely on either until this is
            resolved.
          </p>
          <p className="mono break-all text-[10px] text-[var(--text-secondary)]">
            record: {sha256 || "—"}
          </p>
          <p className="mono break-all text-[10px] text-[var(--text-secondary)]">
            custody: {check.custodyDigest}
          </p>
        </div>
      ) : (
        <p className="mono mt-1.5 break-all text-[10px] text-[var(--text-secondary)]">
          {sha256 || "No hash on record"}
        </p>
      )}
    </div>
  );
}

function RecoveredPanel({
  caseId,
  recovered,
}: {
  caseId: string;
  recovered: RecoveredState;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          Recovered from this source
        </p>
        {/* The Recovery page selects its source from its own state, so this is
            a plain navigation, not a pre-filter — no query param is passed that
            the page would silently ignore. */}
        <Link
          to={`/cases/${caseId}/recover`}
          className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-[var(--accent-500)] hover:underline"
        >
          Recovery
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      </div>

      {recovered.status === "loading" ? (
        <Skeleton className="h-9 w-full" />
      ) : recovered.status === "error" ? (
        <p className="text-[11px] text-[var(--status-warning)]">
          Could not read the recovery output for this source:{" "}
          {recovered.message}
        </p>
      ) : recovered.data.total === 0 ? (
        <p className="text-[12px] text-[var(--text-tertiary)]">
          No recovery output is recorded against this source yet.
        </p>
      ) : (
        <>
          <p className="text-[20px] font-semibold leading-none text-[var(--text-primary)]">
            {recovered.data.total.toLocaleString()}
            <span className="ml-1.5 text-[12px] font-normal text-[var(--text-secondary)]">
              {recovered.data.total === 1 ? "artefact" : "artefacts"}
            </span>
          </p>
          <ul className="mt-2 space-y-1 text-[11px] text-[var(--text-secondary)]">
            <li className="flex justify-between gap-2">
              <span>Recordings (index-backed)</span>
              <span className="mono">{recovered.data.recordings}</span>
            </li>
            <li className="flex justify-between gap-2">
              <span>Filesystem undelete</span>
              <span className="mono">{recovered.data.filesystemUndelete}</span>
            </li>
            <li className="flex justify-between gap-2">
              <span>Stream carves</span>
              <span className="mono">{recovered.data.carves}</span>
            </li>
            <li
              className="flex justify-between gap-2 border-t pt-1"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <span>Of which deleted</span>
              <span className="mono">{recovered.data.deleted}</span>
            </li>
          </ul>
        </>
      )}
    </div>
  );
}

type RecoveredState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: RecoveredFromSource };

/**
 * Recovery output attributable to this source image.
 *
 * Join: recovered_sequences.device_id = devices.id, served read-only by the
 * existing GET /api/v1/devices/{device_id}/sequences. The evidence record's id
 * *is* the device id (engine/app/services/acquisition.py `_device_as_evidence`
 * maps devices.id straight through), so no extra lookup is needed.
 *
 * Counts reuse the Recovery page's own classifiers — `countSegmentKinds` for
 * artifact_kind and `countAllocations` for allocation state — so this panel and
 * the Recovery table can never disagree about the same image.
 */
function useRecoveredFromSource(deviceId: string): RecoveredState {
  const [state, setState] = useState<RecoveredState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    api
      .listDeviceSegments(deviceId)
      .then((response) => {
        if (!active) return;
        const segments = response.segments ?? [];
        const kinds = countSegmentKinds(segments);
        const allocations = countAllocations(segments);
        setState({
          status: "ready",
          data: {
            total: segments.length,
            recordings: kinds.recording,
            carves: kinds.carve,
            filesystemUndelete: kinds.filesystem_undelete,
            deleted: allocations.deleted,
          },
        });
      })
      .catch((error: unknown) => {
        if (!active) return;
        // A source with no recovery run yet is a 404 on the device, not a
        // failure worth alarming the examiner about.
        if (isNotFound(error)) {
          setState({
            status: "ready",
            data: {
              total: 0,
              recordings: 0,
              carves: 0,
              filesystemUndelete: 0,
              deleted: 0,
            },
          });
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "unknown error",
        });
      });
    return () => {
      active = false;
    };
  }, [deviceId]);

  return state;
}
