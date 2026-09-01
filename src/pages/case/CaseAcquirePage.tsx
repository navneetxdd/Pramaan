import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  HardDrive,
  Network,
  Play,
  RotateCcw,
  Server,
  Upload,
} from "lucide-react";

import { Link } from "react-router-dom";

import { toast } from "sonner";

import { useCaseContext } from "@/context/CaseContext";

import { api, type ImagingDisk } from "@/lib/api";

import { subscribeJobEvents, waitForJobCompletion } from "@/lib/sse";

import { HANDLER_FIELD_HINT, HANDLER_FIELD_LABEL } from "@/lib/caseRegistry";

import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";

import {
  HashVerifyBadge,
  type HashVerifyState,
} from "@/components/forensic/HashVerifyBadge";

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

const STEPS = [
  "Select source",
  "Image media",
  "Verify hash",
  "Register evidence",
] as const;

function stepIndex(
  busy: boolean,
  hashState: HashVerifyState,
  hasEvidence: boolean,
): number {
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

  const [oemImages, setOemImages] = useState<
    Array<{ filename: string; size_bytes: number }>
  >([]);

  const [oemDropLabel, setOemDropLabel] = useState("validation_data/oem");

  const [logicalHost, setLogicalHost] = useState("");

  const [logicalPort, setLogicalPort] = useState("80");

  const [logicalUser, setLogicalUser] = useState("");

  const [logicalPassword, setLogicalPassword] = useState("");

  const [logicalVendor, setLogicalVendor] = useState<"hikvision" | "dahua">(
    "hikvision",
  );

  const { setWorking, setIdle } = useActivity();

  const fileInputRef = useRef<HTMLInputElement>(null);

  const evidence = workspace?.evidence ?? [];

  const latest = evidence[0];

  const activeStep = stepIndex(busy, hashState, evidence.length > 0);

  useEffect(() => {
    if (workspace?.case.examiner_name) {
      setActor(workspace.case.examiner_name);
    }
  }, [workspace?.case.examiner_name]);

  const loadSources = useCallback(async () => {
    try {
      const diskResp = await api.listImagingDisks();

      setDisks(diskResp.disks);

      const resumeResp = await api.listResumableAcquisitions(caseId);

      setResumable(resumeResp.devices as ResumableDevice[]);

      const oemResp = await api.listOemImages();

      setOemImages(oemResp.images);

      setOemDropLabel(oemResp.label);
    } catch {
      setDisks([]);

      setOemImages([]);
    }
  }, [caseId]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (latest && hashState === "idle") {
      void verifyLatestHash();
    }
  }, [latest?.id]);

  async function verifyLatestHash() {
    await refresh();

    const ws = await api.getCase(caseId);

    const newest = ws.evidence[0];

    if (!newest?.id) return;

    const check = await api.verify(newest.id);

    setHashState(
      check.ok && check.sha256_ok !== false ? "verified" : "mismatch",
    );
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

  async function handleAcquireUpload() {
    if (!actor.trim()) {
      toast.error("Enter your name for the custody log");

      return;
    }

    if (!file) {
      toast.error("Select an image file");

      return;
    }

    setBusy(true);

    setProgress(8);

    setHashState("pending");

    setWorking("Acquiring evidence…");

    try {
      const result = await api.acquire(caseId, actor.trim(), file);

      setProgress(100);

      await refresh();

      setHashState("pending");

      await verifyLatestHash();

      toast.success("Acquisition complete");
    } catch (err) {
      setHashState("mismatch");

      toast.error(err instanceof Error ? err.message : "Acquisition failed");
    } finally {
      setBusy(false);

      setIdle();
    }
  }

  async function handlePhysicalImaging(
    sourcePath: string,
    sourceType: "file" | "physical",
  ) {
    if (!actor.trim()) {
      toast.error("Enter your name for the custody log");

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

      toast.error(
        err instanceof Error ? err.message : "Physical imaging failed",
        { duration: Infinity },
      );
    } finally {
      setBusy(false);

      setIdle();
    }
  }

  async function handleResume(deviceId: string) {
    if (!actor.trim()) {
      toast.error("Enter your name for the custody log");

      return;
    }

    setBusy(true);

    setWorking("Resuming imaging…");

    try {
      const started = await api.resumeAcquisition(deviceId, actor.trim());

      await waitForJobCompletion(started.job.id);

      toast.success("Imaging complete");

      await refresh();

      await verifyLatestHash();

      void loadSources();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Resume failed");
    } finally {
      setBusy(false);

      setIdle();
    }
  }

  async function handleAcquireOem(filename: string) {
    if (!actor.trim()) {
      toast.error("Enter your name for the custody log");

      return;
    }

    setBusy(true);

    setWorking("Registering operator image…");

    try {
      await api.acquireOemImage(caseId, actor.trim(), filename);

      toast.success("Image registered as evidence");

      await verifyLatestHash();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "OEM acquire failed", {
        duration: Infinity,
      });
    } finally {
      setBusy(false);

      setIdle();
    }
  }

  async function handleLogicalAcquire() {
    if (
      !actor.trim() ||
      !logicalHost.trim() ||
      !logicalUser.trim() ||
      !logicalPassword
    ) {
      toast.error("Handler name, host, user, and password required");

      return;
    }

    const confirmed = window.confirm(
      `Connect to ${logicalHost}:${logicalPort || "80"}? Only proceed if you are authorised to examine this device.`,
    );

    if (!confirmed) return;

    setBusy(true);

    setWorking("Pulling logical clips…");

    try {
      const result = await api.acquireLogical(caseId, {
        actor: actor.trim(),

        host: logicalHost.trim(),

        port: Number(logicalPort) || 80,

        user: logicalUser.trim(),

        password: logicalPassword,

        vendor: logicalVendor,

        max_clips: 4,
      });

      setLogicalPassword("");

      toast.success(`${result.clips_acquired} clip(s) acquired`);

      await verifyLatestHash();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Logical acquisition failed",
        { duration: Infinity },
      );
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
    const items: Array<{
      id: string;
      label: string;
      status: string;
      kind: "evidence" | "resume";
    }> = evidence.map((e) => ({
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
          <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-400)]">
            Step 1 · Preservation
          </p>

          <h1 className="mt-1 text-[20px] font-semibold text-[var(--text-on-dark)]">
            Acquire evidence
          </h1>

          <p className="mt-1 max-w-2xl text-[12px] text-[var(--text-muted-on-dark)]">
            Image or register read-only copies. Source media is never modified —
            hashes are verified before the catalog.
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

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(260px,300px)_1fr_minmax(220px,260px)]">
        <section className="visily-card min-h-0 space-y-4 overflow-y-auto p-4">
          <div>
            <p className="visily-card-title text-[11px]">
              Who is performing this step?
            </p>

            <label className="mt-2 block text-[12px] font-medium text-[var(--text-primary)]">
              {HANDLER_FIELD_LABEL}
            </label>

            <Input
              className="mt-1"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="e.g. SI Sharma"
            />

            <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
              {HANDLER_FIELD_HINT}
            </p>
          </div>

          <div
            className="space-y-2 border-t pt-3"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Upload disk image
            </p>

            <Button
              variant="secondary"
              className="w-full justify-start"
              disabled={busy}
              onClick={() => void handlePickNative()}
            >
              <Upload className="h-4 w-4" />

              {isDesktopApp() ? "Pick image file" : "Choose file"}
            </Button>

            <input
              ref={fileInputRef}
              type="file"
              accept=".bin,.img,.dd,.raw,.e01"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />

            {file ? (
              <p className="mono truncate text-[11px] text-[var(--text-secondary)]">
                {file.name}
              </p>
            ) : null}

            <Button
              className="w-full"
              disabled={busy || !file}
              onClick={() => void handleAcquireUpload()}
            >
              Register upload
            </Button>
          </div>

          <div
            className="space-y-2 border-t pt-3"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Block imaging
            </p>

            <Input
              placeholder="Path or \\.\PhysicalDriveN"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
            />

            <Button
              className="w-full"

              variant="secondary"

              disabled={busy || !filePath.trim()}

              onClick={() =>
                void handlePhysicalImaging(
                  filePath.trim(),
                  filePath.trim().startsWith("\\\\.\\") ? "physical" : "file",
                )
              }
            >
              <Play className="h-4 w-4" />
              Start imaging
            </Button>

            {disks.length > 0 ? (
              <div className="space-y-1">
                {disks.slice(0, 3).map((disk) => (
                  <button
                    key={disk.id}

                    type="button"

                    disabled={busy}

                    className={`flex w-full items-start gap-2 rounded border px-2 py-1.5 text-left text-[11px] ${
                      selectedDisk?.id === disk.id
                        ? "border-[var(--accent-500)] bg-[var(--accent-soft)]"
                        : "border-[var(--border-subtle)]"
                    }`}

                    onClick={() => {
                      setSelectedDisk(disk);

                      setFilePath(disk.path);
                    }}
                  >
                    <HardDrive className="mt-0.5 h-3.5 w-3.5 shrink-0" />

                    <span>
                      <span className="block font-medium">{disk.label}</span>

                      <span className="text-[var(--text-tertiary)]">
                        {formatBytes(disk.size_bytes)} · {disk.bus_type}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div
            className="space-y-2 border-t pt-3"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Operator drop folder
            </p>

            <p className="text-[11px] text-[var(--text-secondary)]">
              Drop E01, DD, or IMG files in{" "}
              <span className="mono">{oemDropLabel}</span>
              {oemDropLabel.startsWith("$") ? null : (
                <>
                  {" "}
                  or set <span className="mono">PRAMAAN_OEM_IMAGE_DIR</span>
                </>
              )}
              .
            </p>

            {oemImages.length === 0 ? (
              <p className="text-[11px] text-[var(--text-tertiary)]">
                No images found — run fetch script or copy media there.
              </p>
            ) : (
              <ul className="space-y-1">
                {oemImages.map((image) => (
                  <li key={image.filename}>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-between"
                      disabled={busy}
                      onClick={() => void handleAcquireOem(image.filename)}
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Server className="h-3.5 w-3.5 shrink-0" />

                        {image.filename}
                      </span>

                      <span className="mono text-[10px]">
                        {formatBytes(image.size_bytes)}
                      </span>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <details
            className="border-t pt-3"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
              Network logical pull (advanced)
            </summary>

            <div className="mt-2 space-y-2">
              <p className="text-[11px] text-amber-900">
                Clips only — no deleted/unallocated recovery.
              </p>

              <Input
                placeholder="NVR IP"
                value={logicalHost}
                onChange={(e) => setLogicalHost(e.target.value)}
              />

              <Input
                placeholder="Port"
                value={logicalPort}
                onChange={(e) => setLogicalPort(e.target.value)}
              />

              <Input
                placeholder="Username"
                value={logicalUser}
                onChange={(e) => setLogicalUser(e.target.value)}
              />

              <Input
                type="password"
                placeholder="Password (not stored)"
                value={logicalPassword}
                onChange={(e) => setLogicalPassword(e.target.value)}
              />

              <select
                className="field w-full"
                value={logicalVendor}
                onChange={(e) =>
                  setLogicalVendor(e.target.value as typeof logicalVendor)
                }
              >
                <option value="hikvision">Hikvision ISAPI</option>

                <option value="dahua">Dahua CGI</option>
              </select>

              <Button
                className="w-full"
                variant="secondary"
                disabled={busy}
                onClick={() => void handleLogicalAcquire()}
              >
                <Network className="h-4 w-4" />
                Pull clips
              </Button>
            </div>
          </details>
        </section>

        <section className="visily-card flex flex-col p-5">
          <p className="visily-card-title mb-4 text-[11px]">
            Acquisition status
          </p>

          {busy ? (
            <div className="space-y-4">
              <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-3)]">
                <div
                  className="h-full bg-[var(--accent-500)] transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>

              <JobProgressCard
                title="Imaging in progress"
                subtitle={statusMessage || "Reading source…"}
                status="running"
                progress={progress}
              />
            </div>
          ) : latest ? (
            <div className="space-y-4">
              <HashVerifyBadge state={hashState} />

              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-4">
                <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
                  Registered evidence
                </p>

                <p className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">
                  {latest.filename}
                </p>

                <dl className="mt-3 space-y-2 font-mono text-[11px] text-[var(--text-secondary)]">
                  <div className="flex justify-between gap-4">
                    <dt>Size</dt>

                    <dd>{formatBytes(latest.size_bytes)}</dd>
                  </div>

                  <div className="flex justify-between gap-4">
                    <dt>SHA-256</dt>

                    <dd className="truncate">{latest.sha256}</dd>
                  </div>

                  <div className="flex justify-between gap-4">
                    <dt>MD5</dt>

                    <dd>{latest.md5 ?? "—"}</dd>
                  </div>

                  <div className="flex justify-between gap-4">
                    <dt>Status</dt>

                    <dd>{latest.acquisition_status ?? "complete"}</dd>
                  </div>
                </dl>
              </div>

              {hashState === "verified" ? (
                <Button asChild className="w-full sm:w-auto">
                  <Link to={`/cases/${caseId}/device-id`}>
                    Continue to identification →
                  </Link>
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center py-12 text-center">
              <p className="text-[15px] font-medium text-[var(--text-primary)]">
                No evidence registered
              </p>

              <p className="mt-2 max-w-sm text-[13px] text-[var(--text-secondary)]">
                Choose a source on the left — upload, image a path, or register
                a file from the operator drop folder.
              </p>
            </div>
          )}
        </section>

        <aside className="visily-card flex min-h-0 flex-col">
          <div className="visily-card-header">
            <span className="visily-card-title">This case</span>

            <span className="mono text-[10px] text-[var(--text-tertiary)]">
              {queueItems.length}
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {queueItems.length === 0 ? (
              <p className="p-3 text-[12px] text-[var(--text-tertiary)]">
                Evidence items appear here after acquisition.
              </p>
            ) : (
              <ul className="space-y-2">
                {queueItems.map((item) => (
                  <li
                    key={item.id}
                    className="rounded border border-[var(--border-subtle)] p-3"
                  >
                    <p className="truncate text-[12px] font-medium">
                      {item.label}
                    </p>

                    <p className="mono mt-1 text-[10px] text-[var(--text-tertiary)]">
                      {shortHash(item.id)}
                    </p>

                    <div className="mt-2 flex items-center justify-between">
                      <span className="rounded bg-emerald-50 px-2 py-0.5 text-[9px] font-bold uppercase text-emerald-800">
                        {item.status}
                      </span>

                      {item.kind === "resume" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => void handleResume(item.id)}
                        >
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
