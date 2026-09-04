import { useLayoutEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "@/lib/utils";

type Column<T> = {
  key: string;
  header: string;
  className?: string;
  /**
   * CSS grid track for this column, e.g. "72px" or "minmax(150px, 1.5fr)".
   * Defaults to an equal flexible share, which is what every call site got
   * before widths existed.
   */
  width?: string;
  /** Makes the header a sort control. Requires `sortValue`. */
  sortable?: boolean;
  /** Comparable value for this row when sorting by this column. */
  sortValue?: (row: T) => string | number;
  cell: (row: T, index: number) => React.ReactNode;
};

type VirtualTableProps<T> = {
  rows: T[];
  columns: Column<T>[];
  /** Estimated row height. Real heights are measured, so multi-line cells fit. */
  rowHeight?: number;
  maxHeight?: number;
  emptyMessage?: string;
  getRowKey?: (row: T, index: number) => string;
  selectedRowKey?: string | null;
  onRowClick?: (row: T, index: number) => void;
  /** Extra classes per row, e.g. to mark forensically significant rows. */
  getRowClassName?: (row: T, index: number) => string | undefined;
  /** Native title attribute per row, surfaced as a hover tooltip. */
  getRowTitle?: (row: T, index: number) => string | undefined;
  /**
   * Width below which the table scrolls horizontally instead of crushing
   * columns. Omit to keep the table fluid at any width.
   */
  minWidth?: number | string;
  /** Key of the column currently sorted by, if any. */
  sortKey?: string | null;
  sortDir?: "asc" | "desc";
  /** Called when a sortable header is activated. */
  onSortChange?: (key: string) => void;
};

const DEFAULT_TRACK = "minmax(0, 1fr)";

export function VirtualTable<T>({
  rows,
  columns,
  rowHeight = 36,
  maxHeight = 480,
  emptyMessage = "No rows",
  getRowKey,
  selectedRowKey,
  onRowClick,
  getRowClassName,
  getRowTitle,
  minWidth,
  sortKey = null,
  sortDir = "asc",
  onSortChange,
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);

  /**
   * Width of the body pane's vertical scrollbar.
   *
   * The header sits outside the scrolling pane, so once the body overflows, its
   * scrollbar narrows the body's content box while the header still spans the
   * full width — every column drifts by the scrollbar width. Reserving the same
   * gutter on the header keeps the two grids identical. Measured rather than
   * assumed, because it is 0 on overlay-scrollbar platforms and ~15px on
   * Windows.
   */
  const [scrollbarGutter, setScrollbarGutter] = useState(0);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  // Depends on the measured total size, not just the row count: rows start at
  // their estimated height and grow once measured, so the pane can begin
  // overflowing after mount. A ResizeObserver alone misses that — the pane's
  // border box never changes, only its scroll height does.
  const totalSize = virtualizer.getTotalSize();
  useLayoutEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const measure = () => setScrollbarGutter(el.offsetWidth - el.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [rows.length, maxHeight, totalSize]);

  if (rows.length === 0) {
    return (
      <p className="p-4 text-[13px] text-[var(--text-tertiary)]">
        {emptyMessage}
      </p>
    );
  }

  // One template drives the header and every row, so they cannot drift apart.
  const gridTemplateColumns = columns
    .map((col) => col.width ?? DEFAULT_TRACK)
    .join(" ");

  return (
    // Single horizontal scroller wrapping header + body keeps them in lockstep.
    <div className="overflow-x-auto">
      <div style={{ minWidth }}>
        <div
          role="row"
          className="grid border-b border-[var(--border-subtle)] bg-[var(--surface-3)]"
          style={{ gridTemplateColumns, paddingRight: scrollbarGutter }}
        >
          {columns.map((col) => {
            const active = sortKey === col.key;
            const canSort = Boolean(col.sortable && onSortChange);
            return (
              <div
                key={col.key}
                role="columnheader"
                aria-sort={
                  active
                    ? sortDir === "asc"
                      ? "ascending"
                      : "descending"
                    : canSort
                      ? "none"
                      : undefined
                }
                className="flex items-center px-3 py-2 text-[11px] font-semibold uppercase leading-tight tracking-[0.02em] text-[var(--text-tertiary)]"
              >
                {canSort ? (
                  <button
                    type="button"
                    onClick={() => onSortChange?.(col.key)}
                    className={cn(
                      "-mx-1 flex items-center gap-1 rounded px-1 py-0.5 text-left uppercase transition-colors hover:text-[var(--text-secondary)]",
                      active ? "text-[var(--accent-600)]" : "",
                    )}
                    title={`Sort by ${col.header}`}
                  >
                    <span>{col.header}</span>
                    <span
                      aria-hidden="true"
                      className="text-[9px] leading-none"
                    >
                      {active ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                    </span>
                  </button>
                ) : (
                  col.header
                )}
              </div>
            );
          })}
        </div>

        {/* overflowX must be explicit: with only overflowY set, CSS promotes the
            other axis from `visible` to `auto`, so this pane grew its own
            horizontal scrollbar underneath the outer one. Horizontal scrolling
            belongs to the wrapper, which moves the header and body together. */}
        <div
          ref={parentRef}
          style={{ maxHeight, overflowY: "auto", overflowX: "hidden" }}
        >
          <div style={{ height: totalSize, position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = rows[item.index];
              const rowKey = getRowKey?.(row, item.index) ?? String(item.index);
              const selected =
                selectedRowKey != null && rowKey === selectedRowKey;
              return (
                <div
                  key={item.key}
                  // Measured rather than assumed: stacked cells set the height.
                  data-index={item.index}
                  ref={virtualizer.measureElement}
                  role={onRowClick ? "button" : "row"}
                  tabIndex={onRowClick ? 0 : undefined}
                  title={getRowTitle?.(row, item.index)}
                  onClick={
                    onRowClick ? () => onRowClick(row, item.index) : undefined
                  }
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onRowClick(row, item.index);
                          }
                        }
                      : undefined
                  }
                  className={cn(
                    "absolute left-0 grid w-full border-b border-[var(--border-subtle)] text-[13px]",
                    item.index % 2
                      ? "bg-[var(--surface-2)]"
                      : "bg-[var(--surface-1)]",
                    selected
                      ? "ring-1 ring-inset ring-[var(--accent-500)]"
                      : "",
                    onRowClick
                      ? "cursor-pointer hover:bg-[var(--surface-3)]"
                      : "",
                    getRowClassName?.(row, item.index),
                  )}
                  style={{
                    minHeight: rowHeight,
                    transform: `translateY(${item.start}px)`,
                    gridTemplateColumns,
                  }}
                >
                  {columns.map((col) => (
                    <div
                      key={col.key}
                      role="cell"
                      className={cn(
                        // min-w-0 lets long values wrap instead of forcing the
                        // grid track wider; height comes from the content.
                        "flex min-w-0 items-center break-words px-3 py-1.5",
                        col.className,
                      )}
                    >
                      {col.cell(row, item.index)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
