import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FlaskConical, HardDrive, Play, RotateCcw, Upload } from "lucide-react";
import { toast } from "sonner";
import { useCaseContext } from "@/context/CaseContext";
import { api, type ImagingDisk } from "@/lib/api";
import { subscribeJobEvents } from "@/lib/sse";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScanSweep } from "@/components/forensic/ScanSweep";
import { HashVerifyBadge, type HashVerifyState } from "@/components/forensic/HashVerifyBadge";
import { useActivity } from "@/context/ActivityContext";
import { isDesktopApp, pickDiskImage } from "@/lib/desktop";
import { formatBytes, shortHash } from "@/lib/utils";
import { JobProgressCard } from "@/components/visily/JobProgressCard";

type ResumableDevice = {
  id: string;
  acquisition_status: string;
  bad_sector_map_json?: string | null;
  image_path?: string;
};

const STEPS = ["Select source", "Image media", "Verify hash", "Register evidence"] as const;

function stepIndex(busy: boolean, hashState: HashVerifyState, hasEvidence: boolean): number {
  if (hasEvidence && hashState === "verified") return 3;
  if (hashState === "verified" || hashState === "mismatch") return 2;
  if (busy) return 1;
  return 0;
}

export function CaseAcquirePage() {
  const { caseId, workspace, refresh } = useCaseContext();
  const [actor, setActor] = useState(workspace?.case.examiner_name ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [filePath, setFilePath] = useState("");
  const [disks, setDisks] = useState<ImagingDisk[]>([]);
  const [selectedDisk, setSelectedDisk] = useState<ImagingDisk | null>(null);
  const [resumable, setResumable] = useState<ResumableDevice[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [hashState, setHashState] = useState<HashVerifyState>("idle");
  const { setWorking, setIdle } = useActivity();

  const fileInputRef = useRef<HTMLInputElement>(null);

  const evidence = workspace?.evidence ?? [];
  const latest = evidence[0];
  const activeStep = stepIndex(busy, hashState, evidence.length > 0);

  const loadSources = useCallback(async () => {
    try {
      const diskResp = await api.listImagingDisks();
      setDisks(diskResp.disks);
      const resumeResp = await api.listResumableAcquisitions(caseId);
      setResumable(resumeResp.devices as ResumableDevice[]);
    } catch {
      setDisks([]);
    }
  }, [caseId]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  async function verifyLatestHash() {
    await refresh();
    const ws = await api.getCase(caseId);
    const newest = ws.evidence[0];
    if (!newest?.id) return;
    const check = await api.verify(newest.id);
    setHashState(check.ok && check.sha256_ok !== false ? "verified" : "mismatch");
  }

  function trackJob(jobId: string) {
    return subscribeJobEvents(jobId, {
      onEvent: (event) => {
        if (typeof event.progress === "number") setProgress(event.progress);
        if (event.message) setStatusMessage(event.message);
        if (event.status === "completed") {
          setProgress(100);
          toast.success("Imaging complete");
          void verifyLatestHash();
          void loadSources();
        }
        if (event.status === "failed") {
          setHashState("mismatch");
          toast.error(event.error ?? "Imaging failed", { duration: Infinity });
        }
        if (event.status === "interrupted") {
          toast.warning("Imaging interrupted — resume when ready");
          void loadSources();
        }
      },
      onError: (err) => toast.error(err.message, { duration: Infinity }),
    });
  }

  async function handleAcquire(source: "upload" | "specimen" | "honeywell" | "hikvision") {
    if (!actor.trim()) {
      toast.error("Examiner name required");
      return;
    }
    if (source === "upload" && !file) {
      toast.error("Select an image file");
      return;
    }

    setBusy(true);
    setProgress(8);
    setHashState("pending");
    setWorking("Acquiring evidence…");

    try {
      if (source === "specimen") {
        await api.createLabSpecimen(caseId, actor.trim(), "dahua");
        setProgress(100);
      } else if (source === "honeywell") {
        await api.createLabSpecimen(caseId, actor.trim(), "honeywell");
        setProgress(100);
      } else if (source === "hikvision") {
        await api.createLabSpecimen(caseId, actor.trim(), "hikvision");
        setProgress(100);
      } else if (file) {
        const result = await api.acquire(caseId, actor.trim(), file);
        setProgress(100);
        setHashState(result.evidence.sha256 ? "verified" : "mismatch");
      }
      toast.success("Acquisition complete");
      await verifyLatestHash();
    } catch (err) {
      setHashState("mismatch");
      toast.error(err instanceof Error ? err.message : "Acquisition failed", { duration: Infinity });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  async function handlePhysicalImaging(sourcePath: string, sourceType: "file" | "physical") {
    if (!actor.trim()) {
      toast.error("Examiner name required");
      return;
    }
    setBusy(true);
    setProgress(0);
    setStatusMessage("Starting read-only imaging…");
    setHashState("pending");
    setWorking("Block imaging (read-only source)…");

    try {
      const started = await api.acquirePhysical(caseId, {
        actor: actor.trim(),
        source_path: sourcePath,
        source_type: sourceType,
      });
      await new Promise<void>((resolve, reject) => {
        const inner = subscribeJobEvents(started.job.id, {
          onEvent: (event) => {
            if (typeof event.progress === "number") setProgress(event.progress);
            if (event.message) setStatusMessage(event.message);
            if (event.status === "completed") {
              setProgress(100);
              void verifyLatestHash();
              inner();
              resolve();
            }
            if (event.status === "failed" || event.status === "interrupted") {
              setHashState("mismatch");
              inner();
              reject(new Error(event.error ?? `Imaging ${event.status}`));
            }
          },
          onError: (err) => {
            inner();
            reject(err);
          },
        });
      });
      await refresh();
    } catch (err) {
      setHashState("mismatch");
      toast.error(err instanceof Error ? err.message : "Physical imaging failed", { duration: Infinity });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  async function handleResume(deviceId: string) {
    if (!actor.trim()) {
      toast.error("Examiner name required");
      return;
    }
    setBusy(true);
    setWorking("Resuming imaging…");
    try {
      const started = await api.resumeAcquisition(deviceId, actor.trim());
      trackJob(started.job.id);
      toast.message("Resume started");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Resume failed", { duration: Infinity });
    } finally {
      setBusy(false);
      setIdle();
    }
  }

  async function handlePickNative() {
    if (isDesktopApp()) {
      const picked = await pickDiskImage();
      if (picked) setFile(picked);
      return;
    }
    fileInputRef.current?.click();
  }

  const queueItems = useMemo(() => {
    const items: Array<{ id: string; label: string; status: string; kind: "evidence" | "resume" }> = evidence.map((e) => ({
      id: e.id,
      label: e.filename,
      status: e.acquisition_status ?? "registered",
      kind: "evidence" as const,
    }));
    for (const dev of resumable) {
      if (!items.some((i) => i.id === dev.id)) {
        items.push({
          id: dev.id,
          label: dev.image_path ?? dev.id.slice(0, 12),
          status: dev.acquisition_status,
          kind: "resume" as const,
        });
      }
    }
    return items;
  }, [evidence, resumable]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="visily-hero-dark px-5 py-4">
        <div className="visily-hero-dark-bg" aria-hidden />
        <div className="relative z-[1]">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">Preservation workflow</p>
          <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">Acquisition & preservation</h1>
          <p className="mt-1 max-w-2xl text-[12px] text-[var(--text-muted-on-dark)]">
            Read-only imaging — source media is never written. Hashes are computed before evidence enters the catalog.
          </p>
          <ol className="mt-4 flex flex-wrap gap-2">
            {STEPS.map((label, idx) => (
              <li
                key={label}
                className={`rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wide ${
                  idx <= activeStep
                    ? "bg-[var(--accent-500)] text-white"
                    : "border border-white/20 text-[var(--text-muted-on-dark)]"
                }`}
              >
                {idx + 1}. {label}
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[280px_1fr_260px]">
        <section className="visily-card space-y-3 p-3">
          <p className="visily-card-title text-[11px]">Evidence source</p>
          <div className="rounded border border-amber-600/30 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900">
            Engine opens sources read-only. Imaging writes only to case storage.
          </div>
          {(selectedDisk || filePath.startsWith("\\\\.\\")) ? (
            <div className="read-only-banner rounded border border-[var(--status-warning)] bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900">
              Physical source selected — verify write-blocker before imaging.
            </div>
          ) : null}

          <label className="block text-[12px] text-[var(--text-secondary)]">Examiner</label>
          <Input value={actor} onChange={(e) => setActor(e.target.value)} />

          <p className="pt-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">Upload image</p>
          <Button variant="secondary" className="w-full" disabled={busy} onClick={() => void handlePickNative()}>
            <Upload className="h-4 w-4" />
            {isDesktopApp() ? "Pick disk image" : "Choose file"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".bin,.img,.dd,.raw,.e01"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? <p className="mono truncate text-[11px] text-[var(--text-tertiary)]">{file.name}</p> : null}
          <Button className="w-full" disabled={busy} onClick={() => void handleAcquire("upload")}>
            Acquire upload
          </Button>

          <p className="pt-1 text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">Block imaging</p>
          <Input
            placeholder="C:\path\to\image.dd or \\.\PhysicalDrive1"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
          />
          <Button
            className="w-full"
            variant="secondary"
            disabled={busy || !filePath.trim()}
            onClick={() =>
              void handlePhysicalImaging(filePath.trim(), filePath.trim().startsWith("\\\\.\\") ? "physical" : "file")
            }
          >
            <Play className="h-4 w-4" />
            Start block imaging
          </Button>

          {disks.length > 0 ? (
            <div className="space-y-1">
              <p className="text-[11px] text-[var(--text-tertiary)]">Detected disks ({disks.length})</p>
              {disks.slice(0, 4).map((disk) => (
                <button
                  key={disk.id}
                  type="button"
                  disabled={busy}
                  className={`flex w-full items-start gap-2 rounded border px-2 py-1.5 text-left text-[11px] ${
                    selectedDisk?.id === disk.id
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                      : "border-[var(--border-subtle)] hover:border-[var(--border-strong)]"
                  }`}
                  onClick={() => {
                    setSelectedDisk(disk);
                    setFilePath(disk.path);
                  }}
                >
                  <HardDrive className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    <span className="block font-medium">{disk.label}</span>
                    <span className="mono text-[var(--text-tertiary)]">
                      {formatBytes(disk.size_bytes)} · {disk.bus_type}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          <Button variant="secondary" className="w-full" disabled={busy} onClick={() => void handleAcquire("specimen")}>
            <FlaskConical className="h-4 w-4" />
            Known-answer Dahua specimen
          </Button>
          <Button variant="secondary" className="w-full" disabled={busy} onClick={() => void handleAcquire("honeywell")}>
            <FlaskConical className="h-4 w-4" />
            Known-answer Honeywell specimen
          </Button>
          <Button variant="secondary" className="w-full" disabled={busy} onClick={() => void handleAcquire("hikvision")}>
            <FlaskConical className="h-4 w-4" />
            Known-answer Hikvision specimen
          </Button>
        </section>

        <section className="visily-card flex flex-col p-4">
          <p className="visily-card-title mb-3 text-[11px]">Active acquisition</p>
          <div className="flex flex-1 flex-wrap items-center gap-6">
            <ScanSweep progress={busy ? progress : latest ? 100 : 0} />
            <div className="min-w-0 flex-1 space-y-2">
              <HashVerifyBadge state={hashState} />
              {busy ? (
                <JobProgressCard
                  title="Imaging in progress"
                  subtitle={statusMessage || "Reading source media…"}
                  status="running"
                  progress={progress}
                />
              ) : latest ? (
                <>
                  <p className="mono text-[12px] text-[var(--text-secondary)]">
                    Status {latest.acquisition_status ?? "complete"}
                  </p>
                  <p className="mono text-[12px] text-[var(--text-secondary)]">MD5 {shortHash(latest.md5 ?? "—")}</p>
                  <p className="mono text-[12px] text-[var(--text-secondary)]">SHA-256 {shortHash(latest.sha256)}</p>
                  <p className="mono text-[12px] text-[var(--text-tertiary)]">{formatBytes(latest.size_bytes)}</p>
                </>
              ) : (
                <p className="text-[13px] text-[var(--text-tertiary)]">
                  Select a source and start acquisition. Progress and hash verification appear here.
                </p>
              )}
            </div>
          </div>
        </section>

        <aside className="visily-card flex min-h-0 flex-col overflow-hidden">
          <div className="visily-card-header">
            <span className="visily-card-title">Acquisition queue</span>
            <span className="mono text-[10px] text-[var(--text-tertiary)]">{queueItems.length}</span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {queueItems.length === 0 ? (
              <p className="p-3 text-[12px] text-[var(--text-tertiary)]">No acquisitions yet.</p>
            ) : (
              <ul className="space-y-2">
                {queueItems.map((item) => (
                  <li key={item.id} className="rounded border border-[var(--border-subtle)] p-2">
                    <p className="truncate text-[12px] font-medium">{item.label}</p>
                    <p className="mono mt-0.5 text-[10px] text-[var(--text-tertiary)]">{item.id.slice(0, 12)}…</p>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="visily-badge visily-badge-active text-[9px]">{item.status}</span>
                      {item.kind === "resume" ? (
                        <Button size="sm" variant="outline" disabled={busy} onClick={() => void handleResume(item.id)}>
                          <RotateCcw className="h-3 w-3" />
                          Resume
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
