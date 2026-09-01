import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "@/lib/utils";

type Column<T> = {
  key: string;
  header: string;
  className?: string;
  cell: (row: T, index: number) => React.ReactNode;
};

type VirtualTableProps<T> = {
  rows: T[];
  columns: Column<T>[];
  rowHeight?: number;
  maxHeight?: number;
  emptyMessage?: string;
};

export function VirtualTable<T>({
  rows,
  columns,
  rowHeight = 36,
  maxHeight = 480,
  emptyMessage = "No rows",
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  });

  if (rows.length === 0) {
    return <p className="p-4 text-[13px] text-[var(--text-tertiary)]">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-hidden">
      <table className="data-table w-full">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={col.className}>{col.header}</th>
            ))}
          </tr>
        </thead>
      </table>
      <div ref={parentRef} style={{ maxHeight, overflow: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {virtualizer.getVirtualItems().map((item) => {
            const row = rows[item.index];
            return (
              <div
                key={item.key}
                className={cn("absolute left-0 grid w-full border-b border-[var(--border-subtle)] text-[13px]", item.index % 2 ? "bg-[var(--surface-2)]" : "bg-[var(--surface-1)]")}
                style={{
                  height: item.size,
                  transform: `translateY(${item.start}px)`,
                  gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))`,
                }}
              >
                {columns.map((col) => (
                  <div key={col.key} className={cn("flex items-center px-3 py-1", col.className)}>
                    {col.cell(row, item.index)}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
