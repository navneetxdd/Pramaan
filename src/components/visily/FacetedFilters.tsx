import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

export type FilterOption = {
  id: string;
  label: string;
  /** Live count of matching items in the full dataset under the other active
   * filters. Rendered verbatim — never padded or formatted into a fixed width,
   * because a padded count reads as a placeholder. */
  count?: number;
  hint?: string;
};

export type FilterGroup = {
  id: string;
  label: string;
  options: FilterOption[];
};

type FacetedFiltersProps = {
  groups: FilterGroup[];
  selected: Record<string, Set<string>>;
  onToggle: (groupId: string, optionId: string) => void;
  onReset: () => void;
  onQuickDate?: (range: "24h" | "7d") => void;
  loading?: boolean;
};

export function FacetedFilters({
  groups,
  selected,
  onToggle,
  onReset,
  onQuickDate,
  loading = false,
}: FacetedFiltersProps) {
  const activeCount = Object.values(selected).reduce(
    (total, set) => total + set.size,
    0,
  );

  return (
    <aside className="visily-filter-pane overflow-y-auto">
      <div
        className="flex items-center justify-between border-b px-3 py-2.5"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          Faceted filters
        </span>
        <button
          type="button"
          className="text-[10px] font-semibold uppercase text-[var(--accent-500)] hover:underline disabled:cursor-not-allowed disabled:text-[var(--text-tertiary)] disabled:no-underline"
          onClick={onReset}
          disabled={activeCount === 0}
        >
          Reset{activeCount > 0 ? ` (${activeCount})` : ""}
        </button>
      </div>

      {loading ? (
        <div className="space-y-4 p-3">
          {Array.from({ length: 3 }).map((_, group) => (
            <div key={group} className="space-y-2">
              <Skeleton className="h-3 w-24" />
              {Array.from({ length: 3 }).map((_, row) => (
                <Skeleton key={row} className="h-6 w-full" />
              ))}
            </div>
          ))}
          <span className="sr-only">Loading filters…</span>
        </div>
      ) : (
        <div className="space-y-4 p-3">
          {groups.map((group, index) => (
            <div key={group.id}>
              {index > 0 ? <Separator className="mb-3" /> : null}
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                {group.label}
              </p>
              <ul className="space-y-1">
                {group.options.map((option) => {
                  const checked = selected[group.id]?.has(option.id) ?? false;
                  // A facet that would return nothing is disabled rather than
                  // hidden, so the examiner can see the class exists and is
                  // empty rather than wondering whether it was filtered away.
                  const empty = option.count === 0 && !checked;
                  return (
                    <li key={option.id}>
                      <label
                        className={cn(
                          "visily-filter-row",
                          checked && "visily-filter-row-active",
                          empty && "cursor-not-allowed opacity-55",
                        )}
                        title={option.hint}
                      >
                        <Checkbox
                          checked={checked}
                          disabled={empty}
                          onCheckedChange={() => onToggle(group.id, option.id)}
                        />
                        <span className="flex-1 truncate text-[12px] text-[var(--text-secondary)]">
                          {option.label}
                        </span>
                        {option.count !== undefined ? (
                          <span className="mono text-[10px] tabular-nums text-[var(--text-tertiary)]">
                            {option.count}
                          </span>
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
              <button
                type="button"
                className="visily-quick-filter"
                onClick={() => onQuickDate("24h")}
              >
                Last 24 hours
              </button>
              <button
                type="button"
                className="visily-quick-filter"
                onClick={() => onQuickDate("7d")}
              >
                Last 7 days
              </button>
            </div>
          ) : null}
        </div>
      )}
    </aside>
  );
}
