import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Capabilities } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isDesktopApp } from "@/lib/desktop";

export function SettingsPage() {
  const [workingDir, setWorkingDir] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [saving, setSaving] = useState(false);
  const [engineVersion, setEngineVersion] = useState("—");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [acqCaps, setAcqCaps] = useState<Record<string, boolean> | null>(null);

  useEffect(() => {
    void api
      .getSettings()
      .then((s) => {
        setWorkingDir(s.working_directory);
        setFingerprint(s.signing_certificate_fingerprint);
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Failed to load settings", { duration: Infinity }));

    void api.version().then((v) => {
      setEngineVersion(v.version);
      setCapabilities(v.capabilities);
    });
    void api.acquisitionCapabilities().then(setAcqCaps).catch(() => setAcqCaps(null));
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
      const updated = await api.updateSettings({ working_directory: workingDir });
      setFingerprint(updated.signing_certificate_fingerprint);
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed", { duration: Infinity });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1]">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Workstation</p>
          <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Settings</h1>
          <p className="mt-1 text-[12px] text-[var(--text-muted-on-dark)]">
            Engine v{engineVersion} · local forensic workstation (offline, no cloud).
          </p>
        </div>
      </div>

      <section className="visily-card space-y-3 p-4">
        <p className="visily-card-title text-[11px]">Evidence working directory</p>
        <Input value={workingDir} onChange={(e) => setWorkingDir(e.target.value)} />
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => void pickDirectory()}>
            Browse…
          </Button>
          <Button disabled={saving} onClick={() => void save()}>
            Save
          </Button>
        </div>
      </section>

      <section className="visily-card space-y-2 p-4">
        <p className="visily-card-title text-[11px]">Signing certificate</p>
        <p className="mono break-all text-[12px] text-[var(--text-secondary)]">{fingerprint || "—"}</p>
      </section>

      {capabilities ? (
        <section className="visily-card space-y-3 p-4">
          <p className="visily-card-title text-[11px]">Engine capabilities (SIH26150)</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <p className="text-[10px] font-bold uppercase text-[var(--text-tertiary)]">Recovery adapters</p>
              <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                {capabilities.recovery_adapters.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase text-[var(--text-tertiary)]">OEM fingerprints</p>
              <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                {capabilities.oem_fingerprints.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            </div>
          </div>
          {acqCaps ? (
            <p className="text-[12px] text-[var(--text-secondary)]">
              Acquisition: chunked imaging {acqCaps.chunked_imaging ? "✓" : "—"}, resume {acqCaps.checkpoint_resume ? "✓" : "—"},
              E01 input {acqCaps.e01_input ? "✓" : "— (install pyewf)"}
            </p>
          ) : null}
          <div>
            <p className="text-[10px] font-bold uppercase text-[var(--text-tertiary)]">Known limitations</p>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-[12px] text-[var(--text-secondary)]">
              {capabilities.limitations.map((lim) => (
                <li key={lim}>{lim}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </div>
  );
}
