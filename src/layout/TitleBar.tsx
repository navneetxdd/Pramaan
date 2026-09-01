import { useEffect, useState } from "react";
import { Minus, Square, X, Copy } from "lucide-react";
import { PramaanMark } from "@/components/brand/PramaanMark";
import { closeWindow, isDesktopApp, minimizeWindow, startWindowDrag, toggleMaximizeWindow } from "@/lib/desktop";
import { useBreadcrumb } from "./ModuleSidebar";

export function TitleBar() {
  const { section, page } = useBreadcrumb();
  const [desktop, setDesktop] = useState(false);
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    setDesktop(isDesktopApp());
  }, []);

  if (!desktop) return null;

  return (
    <div
      className="titlebar flex h-9 shrink-0 select-none items-center justify-between border-b px-3"
      style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)" }}
      data-tauri-drag-region
      onMouseDown={(e) => {
        if ((e.target as HTMLElement).closest("[data-tauri-no-drag]")) return;
        void startWindowDrag();
      }}
    >
      <div className="flex items-center gap-2.5" data-tauri-drag-region>
        <PramaanMark variant="brand" className="h-4 w-4" />
        <span className="text-[12px] font-medium text-[var(--text-primary)]">Pramaan</span>
        <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
          {section} / {page}
        </span>
      </div>

      <div className="flex items-center gap-1" data-tauri-no-drag>
        <button type="button" className="titlebar-btn" onClick={() => void minimizeWindow()} aria-label="Minimize">
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="titlebar-btn"
          onClick={() => {
            void toggleMaximizeWindow().then(() => setMaximized((m) => !m));
          }}
          aria-label={maximized ? "Restore" : "Maximize"}
        >
          {maximized ? <Copy className="h-3 w-3" /> : <Square className="h-3 w-3" />}
        </button>
        <button type="button" className="titlebar-btn titlebar-btn-close" onClick={() => void closeWindow()} aria-label="Close">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
