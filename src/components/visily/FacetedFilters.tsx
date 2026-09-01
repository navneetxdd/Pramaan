import { cn } from "@/lib/utils";

export type FilterGroup = {
  id: string;
  label: string;
  options: Array<{ id: string; label: string; count?: number }>;
};

type FacetedFiltersProps = {
  groups: FilterGroup[];
  selected: Record<string, Set<string>>;
  onToggle: (groupId: string, optionId: string) => void;
  onReset: () => void;
  onQuickDate?: (range: "24h" | "7d") => void;
};

export function FacetedFilters({ groups, selected, onToggle, onReset, onQuickDate }: FacetedFiltersProps) {
  return (
    <aside className="visily-filter-pane">
      <div className="flex items-center justify-between border-b px-3 py-2.5" style={{ borderColor: "var(--border-subtle)" }}>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">Faceted filters</span>
        <button type="button" className="text-[10px] font-semibold uppercase text-[var(--accent-500)] hover:underline" onClick={onReset}>
          Reset
        </button>
      </div>
      <div className="space-y-4 p-3">
        {groups.map((group) => (
          <div key={group.id}>
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">{group.label}</p>
            <ul className="space-y-1">
              {group.options.map((opt) => {
                const checked = selected[group.id]?.has(opt.id) ?? false;
                return (
                  <li key={opt.id}>
                    <label className={cn("visily-filter-row", checked && "visily-filter-row-active")}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => onToggle(group.id, opt.id)}
                        className="h-3.5 w-3.5 rounded border-[var(--border-default)] accent-[var(--accent-500)]"
                      />
                      <span className="flex-1 truncate text-[12px] text-[var(--text-secondary)]">{opt.label}</span>
                      {opt.count !== undefined ? (
                        <span className="mono text-[10px] text-[var(--text-tertiary)]">{opt.count}</span>
                      ) : null}
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {onQuickDate ? (
          <div className="grid grid-cols-2 gap-2 pt-2">
            <button type="button" className="visily-quick-filter" onClick={() => onQuickDate("24h")}>
              Last 24 hours
            </button>
            <button type="button" className="visily-quick-filter" onClick={() => onQuickDate("7d")}>
              Last 7 days
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
