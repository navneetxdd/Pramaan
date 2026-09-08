import { useEffect, useState } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";
import { api, type DatasetEntry } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { subscribeJobEvents } from "@/lib/sse";
import { useActivity } from "@/context/ActivityContext";

export function SettingsPage() {
  const [workingDir, setWorkingDir] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [datasets, setDatasets] = useState<DatasetEntry[]>([]);
  const [fetchingId, setFetchingId] = useState<string | null>(null);
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

  const shortFp = fingerprint
    ? `${fingerprint.slice(0, 8)}…${fingerprint.slice(-8)}`
    : "—";

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <header>
        <h1 className="text-[22px] font-semibold text-[var(--text-primary)]">
          Settings
        </h1>
        <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
          Storage location, AI models, and report signing.
        </p>
      </header>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            Case data folder
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Every case, evidence copy, recovered clip and report is stored here.
            Set at startup; back up this folder to preserve the caseload.
          </p>
        </div>
        <code className="mono block rounded-md border border-[var(--border-subtle)] bg-[var(--surface-3)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          {workingDir || "Could not read the data folder path"}
        </code>
      </section>

      <section className="visily-card space-y-3 p-4">
        <div>
          <p className="text-[13px] font-medium text-[var(--text-primary)]">
            AI models
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            Object, face and re-identification models used by Findings and
            Cross-camera trace. They run entirely on this workstation.
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
                    No models registered on this workstation.
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
            Report signing fingerprint
          </p>
          <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--text-tertiary)]">
            Every signed PDF report carries this fingerprint. Check it against
            the signature shown in your PDF reader to confirm a report was
            produced by this workstation and has not been altered. Self-signed:
            it proves the file is intact, not the examiner's identity.
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
            disabled={!fingerprint}
            className="h-8 shrink-0 px-2"
            onClick={() => void copyFingerprint()}
          >
            <Copy className="h-3.5 w-3.5" />
            Copy
          </Button>
        </div>
      </section>
    </div>
  );
}
