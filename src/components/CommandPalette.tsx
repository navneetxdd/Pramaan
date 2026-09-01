import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { api, type CaseRecord } from "@/lib/api";
import { COMMAND_PALETTE_EVENT } from "@/lib/commandPalette";
import { loadRecentCaseIds, pushRecentCase } from "@/lib/recentCases";
import { Dialog, DialogContent } from "@/components/ui/dialog";

export { pushRecentCase } from "@/lib/recentCases";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(COMMAND_PALETTE_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(COMMAND_PALETTE_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    void api.listCaseRegistry().then(setCases).catch(() => setCases([]));
  }, [open]);

  const recentIds = loadRecentCaseIds();
  const recentCases = recentIds
    .map((id) => cases.find((c) => c.id === id))
    .filter(Boolean) as CaseRecord[];

  function go(path: string) {
    setOpen(false);
    navigate(path);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg p-0">
        <Command
          className="rounded-md bg-[var(--surface-2)] text-[var(--text-primary)]"
          label="Command palette"
        >
          <Command.Input
            placeholder="Search cases and actions…"
            className="w-full border-b border-[var(--border-subtle)] bg-transparent px-3 py-3 text-[13px] outline-none"
          />
          <Command.List className="max-h-72 overflow-y-auto p-2">
            <Command.Empty className="px-2 py-6 text-center text-[13px] text-[var(--text-tertiary)]">
              No matches.
            </Command.Empty>
            <Command.Group heading="Actions" className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
              <Command.Item
                className="cursor-pointer rounded px-2 py-2 text-[13px] aria-selected:bg-[var(--surface-3)]"
                onSelect={() => go("/cases?new=1")}
              >
                New case
              </Command.Item>
              <Command.Item
                className="cursor-pointer rounded px-2 py-2 text-[13px] aria-selected:bg-[var(--surface-3)]"
                onSelect={() => go("/settings")}
              >
                Open settings
              </Command.Item>
            </Command.Group>
            {recentCases.length > 0 ? (
              <Command.Group heading="Recent cases" className="mt-2 text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
                {recentCases.map((c) => (
                  <Command.Item
                    key={c.id}
                    className="cursor-pointer rounded px-2 py-2 text-[13px] aria-selected:bg-[var(--surface-3)]"
                    onSelect={() => go(`/cases/${c.id}`)}
                  >
                    {c.name}
                  </Command.Item>
                ))}
              </Command.Group>
            ) : null}
            <Command.Group heading="All cases" className="mt-2 text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
              {cases.map((c) => (
                <Command.Item
                  key={c.id}
                  className="cursor-pointer rounded px-2 py-2 text-[13px] aria-selected:bg-[var(--surface-3)]"
                  onSelect={() => go(`/cases/${c.id}`)}
                >
                  {c.name} · {c.examiner_name}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
