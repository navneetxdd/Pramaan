import { useEffect, useState } from "react";
import { Copy, Play } from "lucide-react";
import { toast } from "sonner";
import { api, type DatasetEntry } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
  const [datasets, setDatasets] = useState<DatasetEntry[]>([]);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
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

    void api
      .listDatasets()
      .then(setDatasets)
      .catch(() => setDatasets([]));
  }, []);

  async function copyFingerprint() {
    if (!fingerprint) return;
    try {
      await navigator.clipboard.writeText(fingerprint);
      toast.success("Fingerprint copied");
    } catch {
      toast.error("Could not copy to clipboard");
    }
  }

  async function fetchDataset(id: string) {
    setFetchingId(id);
    setWorking(`Fetching ${id}…`);
    try {
      const { job_id } = await api.fetchDataset(id);
      await new Promise<void>((resolve, reject) => {
        subscribeJobEvents(job_id, {
          onEvent: (event) => {
            if (event.status === "completed") resolve();
            if (event.status === "failed")
              reject(new Error(event.error || "Fetch failed"));
          },
          onError: reject,
        });
      });
      const updated = await api.listDatasets();
      setDatasets(updated);
      toast.success("Dataset fetched");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Fetch failed");
    } finally {
      setFetchingId(null);
      setIdle();
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
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <header>
        <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">
          Settings
        </h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Workstation storage, validation datasets, and report signing.
        </p>
      </header>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            Data directory
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Set <code className="mono">FORENSIC_WORKSTATION_DATA</code> before
            launching the engine. Runtime relocation is not supported.
          </p>
        </div>
        <code className="mono block rounded-md border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          {workingDir || "—"}
        </code>
      </section>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            Validation datasets
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Public corpora and reference samples — fetched on demand, verified
            by SHA-256 in manifest.
          </p>
        </div>
        <div className="max-h-64 overflow-y-auto rounded-md border border-[var(--border-subtle)]">
          <table className="w-full text-left text-[12px]">
            <thead className="sticky top-0 bg-[var(--surface-2)] text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="px-2 py-1.5">Dataset</th>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {datasets.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="px-2 py-3 text-[var(--text-tertiary)]"
                  >
                    No manifest entries — run fetch_validation_assets.py
                    locally.
                  </td>
                </tr>
              ) : (
                datasets.map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-[var(--border-subtle)]"
                  >
                    <td className="px-2 py-2">
                      <p className="font-medium text-[var(--text-primary)]">
                        {row.id}
                      </p>
                      <p className="text-[11px] text-[var(--text-tertiary)]">
                        {row.purpose}
                      </p>
                    </td>
                    <td className="px-2 py-2">
                      <span
                        className={
                          row.verified
                            ? "text-[var(--status-success)]"
                            : row.present
                              ? "text-[var(--status-warning)]"
                              : "text-[var(--text-tertiary)]"
                        }
                      >
                        {row.verified
                          ? "verified"
                          : row.present
                            ? "present"
                            : "missing"}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right">
                      {!row.verified ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={fetchingId === row.id}
                          onClick={() => void fetchDataset(row.id)}
                        >
                          {fetchingId === row.id ? "…" : "Fetch"}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            PDF signing fingerprint
          </p>
          <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--text-tertiary)]">
            Compare this value to signature properties in your PDF reader.
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
            Runs OEM fixtures including playable-export verification when assets
            are present.
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
