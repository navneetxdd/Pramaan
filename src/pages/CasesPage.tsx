import { useEffect, useState } from "react";
import { FolderOpen, Plus, Upload } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { classifyImportFile, IMPORT_FILE_ACCEPT } from "@/lib/importFormats";
import {
  pushRecentCase,
  mostRecentCaseId,
  pruneRecentCases,
} from "@/lib/recentCases";
import {
  CaseRegistryCard,
  type CaseRegistryRow,
} from "@/components/case/CaseRegistryCard";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

async function loadEngineVersion(attempts = 3) {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await api.version();
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await new Promise((resolve) =>
          window.setTimeout(resolve, 500 * (attempt + 1)),
        );
      }
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Engine health check failed");
}

export function CasesPage() {
  const [cases, setCases] = useState<CaseRegistryRow[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [handler, setHandler] = useState("");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importHandler, setImportHandler] = useState("");
  const [importCaseTitle, setImportCaseTitle] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    if (params.get("new") === "1") {
      setDialogOpen(true);
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  async function load() {
    setLoading(true);
    setEngineOnline(null);
    const [caseResult, versionResult] = await Promise.allSettled([
      api.listCaseRegistry(),
      loadEngineVersion(),
    ]);

    if (caseResult.status === "fulfilled") {
      setCases(caseResult.value);
      pruneRecentCases(caseResult.value.map((c) => c.id));
    } else {
      setCases([]);
      toast.error(
        caseResult.reason instanceof Error
          ? caseResult.reason.message
          : "Failed to load cases",
      );
    }

    if (versionResult.status === "fulfilled") {
      setEngineOnline(versionResult.value.status === "ok");
    } else {
      setEngineOnline(false);
    }
    setLoading(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = cases.filter(
    (c) =>
      c.name.toLowerCase().includes(filter.toLowerCase()) ||
      c.examiner_name.toLowerCase().includes(filter.toLowerCase()) ||
      (c.notes ?? "").toLowerCase().includes(filter.toLowerCase()),
  );

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !handler.trim()) return;
    setCreating(true);
    try {
      const created = await api.createCase({
        name: name.trim(),
        examiner_name: handler.trim(),
        notes: notes.trim() || undefined,
      });
      pushRecentCase(created.id);
      toast.success("Case opened");
      setDialogOpen(false);
      setName("");
      setHandler("");
      setNotes("");
      navigate(`/cases/${created.id}/acquire`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create case");
    } finally {
      setCreating(false);
    }
  }

  function resetImportDialog() {
    setImportHandler("");
    setImportCaseTitle("");
    setImportFile(null);
  }

  async function handleImportSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!importFile) {
      toast.error("Select a file to import");
      return;
    }
    if (!importHandler.trim()) {
      toast.error("Enter the handler name");
      return;
    }

    const kind = classifyImportFile(importFile);
    if (kind === "unknown") {
      toast.error(
        "Unsupported file — use E01, DD, IMG, RAW, BIN, or a signed case export (.zip)",
      );
      return;
    }

    if (kind === "evidence" && !importCaseTitle.trim()) {
      toast.error("Enter a case title for this evidence");
      return;
    }

    setImporting(true);
    try {
      if (kind === "evidence") {
        const created = await api.createCase({
          name: importCaseTitle.trim(),
          examiner_name: importHandler.trim(),
        });
        await api.acquire(created.id, importHandler.trim(), importFile);
        pushRecentCase(created.id);
        toast.success(
          "Evidence ingested — parsers will identify the source format",
        );
        setImportDialogOpen(false);
        resetImportDialog();
        await load();
        navigate(`/cases/${created.id}/acquire`);
      } else {
        const result = await api.importCase(importHandler.trim(), importFile);
        toast.success(
          `Case restored — ${result.files_verified} files verified`,
        );
        setImportDialogOpen(false);
        resetImportDialog();
        await load();
        navigate(`/cases/${result.case_id}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  const importKind = importFile ? classifyImportFile(importFile) : null;
  const recentId = mostRecentCaseId();
  const resumeCase = recentId
    ? filtered.find((c) => c.id === recentId)
    : undefined;

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--accent-600)]">
            Investigations
          </p>
          <h1 className="mt-1 text-[26px] font-semibold text-[var(--text-primary)]">
            Case registry
          </h1>
          <p className="mt-1 max-w-xl text-[13px] text-[var(--text-secondary)]">
            Create or open a case before acquisition, recovery, or reporting.
            Workflow steps unlock in the sidebar once a case is active.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-9 w-52"
            placeholder="Search cases…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={importing}
            onClick={() => setImportDialogOpen(true)}
          >
            <Upload className="h-4 w-4" />
            Import
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            New case
          </Button>
        </div>
      </header>

      {engineOnline === false ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] text-amber-950">
          Engine not running. Start the desktop app or run{" "}
          <code className="mono">python run.py</code> in this folder.
        </div>
      ) : null}

      {resumeCase ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--accent-500)]/25 bg-[var(--accent-soft)] px-4 py-3">
          <div>
            <p className="text-[12px] font-semibold text-[var(--text-primary)]">
              Continue where you left off
            </p>
            <p className="text-[12px] text-[var(--text-secondary)]">
              {resumeCase.name} · handler {resumeCase.examiner_name}
            </p>
          </div>
          <Button asChild>
            <Link
              to={`/cases/${resumeCase.id}`}
              onClick={() => pushRecentCase(resumeCase.id)}
            >
              Open workspace
            </Link>
          </Button>
        </div>
      ) : null}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
            <FolderOpen className="h-4 w-4" />
            {filtered.length} active case{filtered.length === 1 ? "" : "s"}
          </h2>
        </div>

        {loading ? (
          <p className="text-[13px] text-[var(--text-tertiary)]">
            Loading registry…
          </p>
        ) : filtered.length === 0 ? (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-white px-8 py-14 text-center">
            <p className="text-[15px] font-medium text-[var(--text-primary)]">
              No cases yet
            </p>
            <p className="mt-2 text-[13px] text-[var(--text-secondary)]">
              Create a case or import a disk image (E01, DD, IMG, …). The engine
              identifies the vendor format on ingest.
            </p>
            <Button className="mt-4" onClick={() => setDialogOpen(true)}>
              Create first case
            </Button>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {filtered.map((item) => (
              <CaseRegistryCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </section>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <form onSubmit={handleCreate}>
            <DialogHeader>
              <DialogTitle>New case</DialogTitle>
            </DialogHeader>
            <p className="text-[13px] text-[var(--text-secondary)]">
              Opens a new investigation workspace. You will add evidence on the
              next screen.
            </p>
            <div className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <label
                  className="text-[12px] font-medium text-[var(--text-primary)]"
                  htmlFor="case-name"
                >
                  Case title
                </label>
                <Input
                  id="case-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Site or incident name"
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <label
                  className="text-[12px] font-medium text-[var(--text-primary)]"
                  htmlFor="handler"
                >
                  Handler
                </label>
                <Input
                  id="handler"
                  value={handler}
                  onChange={(e) => setHandler(e.target.value)}
                  placeholder="Examiner name"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label
                  className="text-[12px] font-medium text-[var(--text-primary)]"
                  htmlFor="notes"
                >
                  Reference (optional)
                </label>
                <Input
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="FIR, memo, site ID"
                />
              </div>
            </div>
            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={creating}>
                {creating ? "Creating…" : "Create case"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={importDialogOpen}
        onOpenChange={(open) => {
          setImportDialogOpen(open);
          if (!open) resetImportDialog();
        }}
      >
        <DialogContent className="max-w-md">
          <form onSubmit={(e) => void handleImportSubmit(e)}>
            <DialogHeader>
              <DialogTitle>Import</DialogTitle>
            </DialogHeader>
            <p className="text-[13px] text-[var(--text-secondary)]">
              Disk images (E01, DD, IMG, RAW, BIN) are normalized by the engine
              on ingest. A <span className="mono text-[12px]">.zip</span> is
              only for signed case exports from another Pramaan workstation —
              not arbitrary archives.
            </p>
            <div className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <label
                  className="text-[12px] font-medium text-[var(--text-primary)]"
                  htmlFor="import-handler"
                >
                  Handler
                </label>
                <Input
                  id="import-handler"
                  value={importHandler}
                  onChange={(e) => setImportHandler(e.target.value)}
                  placeholder="Examiner name"
                  required
                />
              </div>
              {importKind !== "case_export" ? (
                <div className="space-y-1.5">
                  <label
                    className="text-[12px] font-medium text-[var(--text-primary)]"
                    htmlFor="import-case-title"
                  >
                    Case title
                  </label>
                  <Input
                    id="import-case-title"
                    value={importCaseTitle}
                    onChange={(e) => setImportCaseTitle(e.target.value)}
                    placeholder="Required for disk images"
                    required={importKind === "evidence" || importKind === null}
                  />
                </div>
              ) : null}
              <div className="space-y-1.5">
                <label
                  className="text-[12px] font-medium text-[var(--text-primary)]"
                  htmlFor="import-file"
                >
                  File
                </label>
                <Input
                  id="import-file"
                  type="file"
                  accept={IMPORT_FILE_ACCEPT}
                  disabled={importing}
                  onChange={(e) => {
                    const file = e.target.files?.[0] ?? null;
                    setImportFile(file);
                    if (
                      file &&
                      classifyImportFile(file) === "evidence" &&
                      !importCaseTitle.trim()
                    ) {
                      const stem = file.name.replace(/\.[^.]+$/, "");
                      setImportCaseTitle(stem);
                    }
                  }}
                />
              </div>
            </div>
            <DialogFooter className="mt-6">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setImportDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={importing || !importFile}>
                {importing ? "Importing…" : "Import"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
