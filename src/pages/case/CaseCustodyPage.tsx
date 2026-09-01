import { useEffect, useState } from "react";
import { useCaseContext } from "@/context/CaseContext";
import { api, type CustodyEvent } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { VirtualTable } from "@/components/ui/virtual-table";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { Shield, ShieldCheck, ShieldOff } from "lucide-react";

export function CaseCustodyPage() {
  const { caseId } = useCaseContext();
  const [events, setEvents] = useState<CustodyEvent[]>([]);
  const [intact, setIntact] = useState<boolean | null>(null);

  useEffect(() => {
    void api.custody(caseId).then((d) => {
      setEvents(d.events);
      setIntact(d.chain.ok);
    });
    void api.custodyStatus(caseId).then((s) => setIntact(s.intact));
  }, [caseId]);

  const actors = new Set(events.map((e) => e.actor)).size;

  return (
    <div className="flex flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Audit trail</p>
            <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Chain of custody</h1>
            <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
              Append-only custody log with hash-linked verification for this case.
            </p>
          </div>
          <Badge variant={intact ? "success" : intact === false ? "danger" : "outline"}>
            {intact ? "INTACT" : intact === false ? "BROKEN" : "CHECKING"}
          </Badge>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <DashboardStat label="Custody events" value={String(events.length)} icon={Shield} />
        <DashboardStat label="Unique actors" value={String(actors)} icon={ShieldCheck} tone="info" />
        <DashboardStat
          label="Chain status"
          value={intact ? "Verified" : intact === false ? "Broken" : "Checking"}
          icon={intact === false ? ShieldOff : ShieldCheck}
          tone={intact === false ? "danger" : intact ? "success" : undefined}
        />
      </div>

      <section className="visily-card overflow-hidden">
        <div className="visily-card-header">
          <span className="visily-card-title">Event log</span>
        </div>
        <div className="max-h-[520px]">
          {events.length === 0 ? (
            <p className="p-6 text-[13px] text-[var(--text-secondary)]">No custody events recorded yet.</p>
          ) : (
            <VirtualTable
              rows={events}
              maxHeight={520}
              columns={[
                { key: "n", header: "#", cell: (_, i) => <span className="mono">{i + 1}</span> },
                { key: "time", header: "Time (UTC)", cell: (e) => <span className="mono">{e.created_at}</span> },
                { key: "actor", header: "Actor", cell: (e) => e.actor },
                { key: "action", header: "Action", cell: (e) => <span className="mono">{e.action}</span> },
              ]}
            />
          )}
        </div>
      </section>
    </div>
  );
}
