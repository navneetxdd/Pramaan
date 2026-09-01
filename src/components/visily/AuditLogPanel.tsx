type AuditEntry = {
  id: string | number;
  time: string;
  actor: string;
  action: string;
};

type AuditLogPanelProps = {
  entries: AuditEntry[];
};

export function AuditLogPanel({ entries }: AuditLogPanelProps) {
  return (
    <div className="visily-card h-full">
      <div className="visily-card-header">
        <span className="visily-card-title">Operational audit log</span>
      </div>
      <ul className="max-h-[220px] space-y-0 overflow-y-auto p-2">
        {entries.length === 0 ? (
          <li className="px-2 py-4 text-[12px] text-[var(--text-tertiary)]">No custody events yet.</li>
        ) : (
          entries.slice(0, 8).map((entry) => (
            <li
              key={entry.id}
              className="flex items-start gap-3 rounded-md px-2 py-2 hover:bg-[var(--surface-3)]"
            >
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[var(--accent-400)]" />
              <div className="min-w-0 flex-1">
                <p className="mono text-[10px] text-[var(--text-tertiary)]">{entry.time}</p>
                <p className="text-[12px] text-[var(--text-primary)]">
                  <span className="font-medium">{entry.actor}</span> · {entry.action}
                </p>
              </div>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
