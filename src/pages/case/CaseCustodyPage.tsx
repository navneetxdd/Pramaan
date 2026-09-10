import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCaseContext } from "@/context/CaseContext";
import { api, type CustodyEvent } from "@/lib/api";
import { custodyActionLabel } from "@/lib/integrity";
import { custodyEventsForItem } from "@/lib/evidenceCatalog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VirtualTable } from "@/components/ui/virtual-table";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { PageHeader } from "@/components/visily/PageHeader";
import { Shield, ShieldCheck, ShieldOff } from "lucide-react";

export function CaseCustodyPage() {
  const { caseId, workspace } = useCaseContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [events, setEvents] = useState<CustodyEvent[]>([]);
  const [intact, setIntact] = useState<boolean | null>(null);
  const [firstBrokenRowId, setFirstBrokenRowId] = useState<number | null>(null);

  useEffect(() => {
    void api.custody(caseId).then((d) => {
      setEvents(d.events);
      setIntact(d.chain.intact);
      setFirstBrokenRowId(d.chain.first_broken_row_id);
    });
    void api.custodyStatus(caseId).then((s) => {
      setIntact(s.intact);
      setFirstBrokenRowId(s.first_broken_row_id);
    });
  }, [caseId]);

  // The Evidence Catalog links here with ?evidence=<id> to show the complete
  // set of events for one item. The custody log is written per case, so the
  // only real binding is the hash the row recorded — the same binding the
  // catalog's inspector uses, so both pages agree on what belongs to an item.
  const focusEvidenceId = searchParams.get("evidence");
  const focusItem = useMemo(
    () =>
      focusEvidenceId
        ? (workspace?.evidence.find((e) => e.id === focusEvidenceId) ?? null)
        : null,
    [workspace?.evidence, focusEvidenceId],
  );
  const visibleEvents = useMemo(
    () => (focusItem ? custodyEventsForItem(focusItem, events) : events),
    [focusItem, events],
  );

  function clearFocus() {
    const next = new URLSearchParams(searchParams);
    next.delete("evidence");
    setSearchParams(next, { replace: true });
  }

  // Row number is the position in the complete log, so it stays stable when the
  // table is filtered to one evidence item.
  const rowNumberById = useMemo(() => {
    const map = new Map<number, number>();
    events.forEach((e, index) => map.set(e.id, index + 1));
    return map;
  }, [events]);

  const actors = new Set(events.map((e) => e.actor)).size;
  // The table's "#" column is the row's position (i + 1), not its database id —
  // translate firstBrokenRowId to that same position so the banner and the
  // highlighted row it's pointing at agree with what the table displays.
  const brokenRowPosition =
    firstBrokenRowId != null
      ? events.findIndex((e) => e.id === firstBrokenRowId) + 1 || null
      : null;

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        kicker="Audit trail"
        title="Chain of custody"

        actions={
          <Badge
            variant={
              intact ? "success" : intact === false ? "danger" : "outline"
            }
          >
            {intact ? "INTACT" : intact === false ? "BROKEN" : "CHECKING"}
          </Badge>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <DashboardStat
          label="Custody events"
          value={String(events.length)}
          icon={Shield}
        />
        <DashboardStat
          label="Actors"
          value={String(actors)}
          icon={ShieldCheck}
          tone="info"
        />
        <DashboardStat
          label="Chain status"
          value={intact ? "Verified" : intact === false ? "Broken" : "Checking"}
          icon={intact === false ? ShieldOff : ShieldCheck}
          tone={intact === false ? "danger" : intact ? "success" : undefined}
        />
      </div>

      {intact === false ? (
        <section
          className="visily-card border p-3"
          style={{ borderColor: "var(--status-danger)" }}
        >
          <p className="text-[13px] font-semibold text-[var(--status-danger)]">
            Chain broken
            {brokenRowPosition != null ? ` at row #${brokenRowPosition}` : ""}
          </p>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
            {brokenRowPosition != null
              ? "This is the first row whose stored hash no longer matches its predecessor. Everything from this row onward cannot be trusted as unaltered. Rows before it still verify. It is highlighted below."
              : "The hash chain failed verification, but the exact break point could not be determined."}
          </p>
        </section>
      ) : null}

      {focusEvidenceId ? (
        <section
          className="visily-card border p-3"
          style={{ borderColor: "var(--accent-400)" }}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-[var(--text-primary)]">
                Filtered to one evidence item
                {focusItem ? `: ${focusItem.filename}` : ""}
              </p>
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                {focusItem
                  ? `Showing the ${visibleEvents.length} custody ${visibleEvents.length === 1 ? "row" : "rows"} whose recorded hash is this item's SHA-256. Custody is logged per case, so rows that carry no digest are not attributable to a single item and are not shown here.`
                  : "That evidence id is not in this case, so no rows can be bound to it."}
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={clearFocus}>
              Show all events
            </Button>
          </div>
        </section>
      ) : null}

      <section className="visily-card overflow-hidden">
        <div className="visily-card-header">
          <span className="visily-card-title">Event log</span>
          {focusEvidenceId ? (
            <span className="mono text-[10px] uppercase text-[var(--text-tertiary)]">
              {visibleEvents.length} of {events.length} shown
            </span>
          ) : null}
        </div>
        <div className="max-h-[520px]">
          {events.length === 0 ? (
            <p className="p-6 text-[13px] text-[var(--text-secondary)]">
              No custody events recorded yet.
            </p>
          ) : visibleEvents.length === 0 ? (
            <div className="p-6">
              <p className="text-[13px] text-[var(--text-secondary)]">
                No custody row records a hash for this item. The case log has{" "}
                {events.length} {events.length === 1 ? "event" : "events"} —
                clear the filter to read them.
              </p>
              <Link
                to={`/cases/${caseId}/evidence`}
                className="mt-2 inline-block text-[12px] font-semibold text-[var(--accent-500)] hover:underline"
              >
                Back to evidence catalog
              </Link>
            </div>
          ) : (
            <VirtualTable
              rows={visibleEvents}
              maxHeight={520}
              getRowClassName={(e) =>
                firstBrokenRowId != null && e.id >= firstBrokenRowId
                  ? "custody-row-broken"
                  : undefined
              }
              columns={[
                {
                  key: "n",
                  header: "#",
                  // Position in the full append-only log, not in the filtered
                  // view. A custody row's number is part of its identity and
                  // must not shift because the examiner narrowed the table.
                  cell: (e) => (
                    <span className="mono">
                      {rowNumberById.get(e.id) ?? "—"}
                    </span>
                  ),
                },
                {
                  key: "time",
                  header: "Time (UTC)",
                  cell: (e) => <span className="mono">{e.created_at}</span>,
                },
                { key: "actor", header: "Actor", cell: (e) => e.actor },
                {
                  key: "action",
                  header: "Action",
                  cell: (e) => <span>{custodyActionLabel(e.action)}</span>,
                },
              ]}
            />
          )}
        </div>
      </section>
    </div>
  );
}
