import { useEffect, useState } from "react";
import { useCaseContext } from "@/context/CaseContext";
import { api, type CustodyEvent } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { VirtualTable } from "@/components/ui/virtual-table";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { PageHeader } from "@/components/visily/PageHeader";
import { Shield, ShieldCheck, ShieldOff } from "lucide-react";

export function CaseCustodyPage() {
  const { caseId } = useCaseContext();
  const [events, setEvents] = useState<CustodyEvent[]>([]);
  const [intact, setIntact] = useState<boolean | null>(null);
  const [firstBrokenRowId, setFirstBrokenRowId] = useState<number | null>(null);

  useEffect(() => {
    void api.custody(caseId).then((d) => {
      setEvents(d.events);
      setIntact(d.chain.ok);
      setFirstBrokenRowId(d.chain.first_broken_row_id);
    });
    void api.custodyStatus(caseId).then((s) => {
      setIntact(s.intact);
      setFirstBrokenRowId(s.first_broken_row_id);
    });
  }, [caseId]);

  const actors = new Set(events.map((e) => e.actor)).size;

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        kicker="Audit trail"
        title="Chain of custody"
        subtitle="Append-only custody log with hash-linked verification for this case."
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
          label="Unique actors"
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
            {firstBrokenRowId != null
              ? ` at custody entry #${firstBrokenRowId}`
              : ""}
          </p>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
            {firstBrokenRowId != null
              ? "This is the first row whose stored hash no longer matches its predecessor — everything from this row onward cannot be trusted as unaltered. Rows before it still verify."
              : "The hash chain failed verification, but the exact break point could not be determined."}
          </p>
        </section>
      ) : null}

      <section className="visily-card overflow-hidden">
        <div className="visily-card-header">
          <span className="visily-card-title">Event log</span>
        </div>
        <div className="max-h-[520px]">
          {events.length === 0 ? (
            <p className="p-6 text-[13px] text-[var(--text-secondary)]">
              No custody events recorded yet.
            </p>
          ) : (
            <VirtualTable
              rows={events}
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
                  cell: (_, i) => <span className="mono">{i + 1}</span>,
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
                  cell: (e) => <span className="mono">{e.action}</span>,
                },
              ]}
            />
          )}
        </div>
      </section>
    </div>
  );
}
