import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FolderOpen, Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, type CaseRecord } from "@/lib/api";
import { pushRecentCase, mostRecentCaseId } from "@/lib/recentCases";
import { DashboardStat } from "@/components/visily/DashboardStat";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

async function loadEngineVersion(attempts = 3) {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await api.version();
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 500 * (attempt + 1)));
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Engine health check failed");
}

export function CasesPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [engineOnline, setEngineOnline] = useState<boolean | null>(null);
  const [engineVersion, setEngineVersion] = useState("—");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [examiner, setExaminer] = useState("");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importActor, setImportActor] = useState("");
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
    const [caseResult, versionResult] = await Promise.allSettled([api.listCases(), loadEngineVersion()]);

    if (caseResult.status === "fulfilled") {
      setCases(caseResult.value);
    } else {
      setCases([]);
      toast.error(caseResult.reason instanceof Error ? caseResult.reason.message : "Failed to load cases", {
        duration: Infinity,
      });
    }

    if (versionResult.status === "fulfilled") {
      const version = versionResult.value;
      setEngineOnline(version.status === "ok");
      setEngineVersion(version.version);
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
    if (!name.trim() || !examiner.trim()) return;
    setCreating(true);
    try {
      const created = await api.createCase({
        name: name.trim(),
        examiner_name: examiner.trim(),
        notes: notes.trim() || undefined,
      });
      pushRecentCase(created.id);
      toast.success("Case opened");
      setDialogOpen(false);
      setName("");
      setExaminer("");
      setNotes("");
      navigate(`/cases/${created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create case", { duration: Infinity });
    } finally {
      setCreating(false);
    }
  }

  async function handleImport(file: File | null) {
    if (!file || !importActor.trim()) {
      toast.error("Select a bundle and enter examiner name");
      return;
    }
    setImporting(true);
    try {
      const result = await api.importCase(importActor.trim(), file);
      toast.success(`Imported — ${result.files_verified} files verified`);
      await load();
      navigate(`/cases/${result.case_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Import failed", { duration: Infinity });
    } finally {
      setImporting(false);
    }
  }

  const resumeCase = filtered.find((c) => c.id === mostRecentCaseId()) ?? filtered[0];

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-4">
      {resumeCase ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--accent-500)]/30 bg-[var(--accent-soft)] px-4 py-3">
          <div>
            <p className="text-[13px] font-semibold text-[var(--text-primary)]">Continue investigation</p>
            <p className="text-[12px] text-[var(--text-secondary)]">
              {resumeCase.name} · {resumeCase.examiner_name}
            </p>
          </div>
          <Button asChild>
            <Link to={`/cases/${resumeCase.id}`} onClick={() => pushRecentCase(resumeCase.id)}>
              Open case workspace
            </Link>
          </Button>
        </div>
      ) : null}

      <div className="visily-catalog-toolbar">
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">Cases</h1>
          <p className="mt-0.5 text-[13px] text-[var(--text-secondary)]">Open an investigation or import a signed `.pramaan.zip` bundle.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="h-9 w-48" placeholder="Filter cases…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <Button variant="secondary" disabled={importing} onClick={() => document.getElementById("case-import-input")?.click()}>
            <Upload className="h-4 w-4" />
            Import
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            New case
          </Button>
          <input
            id="case-import-input"
            type="file"
            accept=".zip,.pramaan.zip"
            className="hidden"
            onChange={(e) => void handleImport(e.target.files?.[0] ?? null)}
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <DashboardStat label="Open cases" value={String(filtered.length)} icon={FolderOpen} tone="info" />
        <DashboardStat
          label="Engine"
          value={engineOnline === null ? "Connecting…" : engineOnline ? "Connected" : "Offline"}
          hint={
            engineOnline === null
              ? "Checking local forensic engine"
              : engineOnline
                ? `v${engineVersion} · 127.0.0.1:8787`
                : "Launch Pramaan Desktop or start the local engine"
          }
          icon={FolderOpen}
          tone={engineOnline === null ? "info" : engineOnline ? "success" : "danger"}
        />
      </div>

      <section className="visily-card min-h-[360px]">
        <div className="visily-card-header">
          <span className="visily-card-title">Case registry</span>
          <span className="mono text-[10px] text-[var(--text-tertiary)]">{filtered.length} records</span>
        </div>
        {loading ? (
          <p className="p-6 text-[13px] text-[var(--text-tertiary)]">Loading cases…</p>
        ) : filtered.length === 0 ? (
          <p className="p-10 text-center text-[13px] text-[var(--text-secondary)]">No cases. Create one to begin acquisition.</p>
        ) : (
          <div className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
            {filtered.map((item) => (
              <Link
                key={item.id}
                to={`/cases/${item.id}`}
                onClick={() => pushRecentCase(item.id)}
                className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-[var(--surface-3)]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-semibold text-[var(--text-primary)]">{item.name}</p>
                  <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">{item.examiner_name}</p>
                  {item.notes ? <p className="mono mt-1 text-[10px] text-[var(--text-tertiary)]">{item.notes}</p> : null}
                </div>
                <p className="mono shrink-0 text-[10px] text-[var(--text-tertiary)]">
                  {new Date(item.created_at).toLocaleDateString()}
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <form onSubmit={handleCreate}>
            <DialogHeader>
              <DialogTitle>New case</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div>
                <label className="label" htmlFor="case-name">Case name</label>
                <Input id="case-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label className="label" htmlFor="examiner">Lead examiner</label>
                <Input id="examiner" value={examiner} onChange={(e) => setExaminer(e.target.value)} required />
              </div>
              <div>
                <label className="label" htmlFor="notes">Reference / notes</label>
                <Input id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="FIR / memo" />
              </div>
              <div>
                <label className="label" htmlFor="import-examiner">Import examiner (for bundle import)</label>
                <Input id="import-examiner" value={importActor} onChange={(e) => setImportActor(e.target.value)} placeholder="Required for .pramaan.zip import" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={creating}>{creating ? "Opening…" : "Open case"}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
