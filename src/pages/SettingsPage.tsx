import { useEffect, useState } from "react";
import { Copy, Play } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isDesktopApp } from "@/lib/desktop";
import { subscribeJobEvents } from "@/lib/sse";
import { useActivity } from "@/context/ActivityContext";

type DiagnosticRun = {
  id: string;
  run_at: string;
  results: { passed: boolean };
};

function formatRunTime(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function SettingsPage() {
  const [workingDir, setWorkingDir] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [saving, setSaving] = useState(false);
  const [lastDiagnostic, setLastDiagnostic] = useState<DiagnosticRun | null>(
    null,
  );
  const [runningDiagnostic, setRunningDiagnostic] = useState(false);
  const { setWorking, setIdle } = useActivity();

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        setWorkingDir(s.working_directory);
        setFingerprint(s.signing_certificate_fingerprint);
      })
      .catch((err) =>
        toast.error(
          err instanceof Error ? err.message : "Failed to load settings",
        ),
      );

    void api
      .listToolVerificationResults()
      .then((runs) => setLastDiagnostic(runs[0] ?? null))
      .catch(() => setLastDiagnostic(null));
  }, []);

  async function pickDirectory() {
    if (!isDesktopApp()) {
      toast.error("Directory picker requires the desktop app");
      return;
    }
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ directory: true, multiple: false });
    if (typeof selected === "string") setWorkingDir(selected);
  }

  async function save() {
    setSaving(true);
    try {
      const updated = await api.updateSettings({
        working_directory: workingDir,
      });
      setFingerprint(updated.signing_certificate_fingerprint);
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function copyFingerprint() {
    if (!fingerprint) return;
    try {
      await navigator.clipboard.writeText(fingerprint);
      toast.success("Fingerprint copied");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }

  async function runDiagnostics() {
    setRunningDiagnostic(true);
    setWorking("Running parser checks…");
    try {
      const { job_id } = await api.runToolVerification();
      await new Promise<void>((resolve, reject) => {
        subscribeJobEvents(job_id, {
          onEvent: (event) => {
            if (event.status === "completed") resolve();
            if (event.status === "failed")
              reject(new Error(event.error || "Checks failed"));
          },
          onError: reject,
        });
      });
      const runs = await api.listToolVerificationResults();
      const latest = runs[0] ?? null;
      setLastDiagnostic(latest);
      if (latest?.results?.passed) {
        toast.success("Parser checks passed");
      } else {
        toast.error("One or more checks failed — open the report for detail");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Checks failed");
    } finally {
      setRunningDiagnostic(false);
      setIdle();
    }
  }

  const shortFp = fingerprint
    ? `${fingerprint.slice(0, 8)}…${fingerprint.slice(-8)}`
    : "—";
  const diagnosticOk = Boolean(lastDiagnostic?.results?.passed);

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <header>
        <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">
          Settings
        </h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Workstation storage and report signing.
        </p>
      </header>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            Data directory
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Cases, exports, and custody records.
          </p>
        </div>
        <Input
          value={workingDir}
          onChange={(e) => setWorkingDir(e.target.value)}
        />
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => void pickDirectory()}>
            Browse
          </Button>
          <Button disabled={saving} onClick={() => void save()}>
            Save
          </Button>
        </div>
      </section>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            PDF signing fingerprint
          </p>
          <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--text-tertiary)]">
            Exported reports are signed on this machine. In your PDF reader,
            open signature properties and compare to this value.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2">
          <code
            className="mono min-w-0 flex-1 truncate text-[12px] text-[var(--text-secondary)]"
            title={fingerprint}
          >
            {shortFp}
          </code>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 shrink-0 px-2"
            onClick={() => void copyFingerprint()}
          >
            <Copy className="h-3.5 w-3.5" />
            Copy
          </Button>
        </div>
      </section>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            Parser sanity check
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Optional — runs OEM parser fixtures on this machine. Not required
            for normal case work.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[12px] text-[var(--text-secondary)]">
            {lastDiagnostic
              ? `${diagnosticOk ? "Last run passed" : "Last run had failures"} · ${formatRunTime(lastDiagnostic.run_at)}`
              : "No run on this install yet"}
          </p>
          <div className="flex items-center gap-2">
            {lastDiagnostic ? (
              <a
                href={api.toolVerificationHtmlUrl(lastDiagnostic.id)}
                target="_blank"
                rel="noreferrer"
                className="text-[12px] text-[var(--accent-600)] hover:underline"
              >
                Report
              </a>
            ) : null}
            <Button
              size="sm"
              variant="secondary"
              disabled={runningDiagnostic}
              onClick={() => void runDiagnostics()}
            >
              <Play className="h-3.5 w-3.5" />
              {runningDiagnostic ? "Running…" : "Run"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
