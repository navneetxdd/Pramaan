import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { useCaseContext } from "@/context/CaseContext";
import { PageHeader } from "@/components/visily/PageHeader";
import { Button } from "@/components/ui/button";
import { subscribeJobEvents } from "@/lib/sse";
import {
  api,
  type CrossCameraSource,
  type CrossCameraRun,
  type CrossCameraRunDetail,
  type CrossCameraIdentityDetail,
  type CrossCameraAppearance,
  type CrossCameraMatch,
  type CrossCameraSearchResult,
} from "@/lib/api";

type Models = { detector: boolean; reid: boolean; face: boolean };

const FPS_OPTIONS = [
  { value: 1, label: "1 frame / sec" },
  { value: 2, label: "2 frames / sec" },
  { value: 3, label: "3 frames / sec" },
];

function fmtClock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/* ------------------------------------------------------------------ setup */
function SetupSection({
  sources,
  models,
  busy,
  onRun,
}: {
  sources: CrossCameraSource[];
  models: Models;
  busy: boolean;
  onRun: (opts: {
    source_keys: string[];
    fps: number;
    match_sensitivity: number;
  }) => void;
}) {
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(sources.map((s) => s.key)),
  );
  const [fps, setFps] = useState(1);
  const [sensitivity, setSensitivity] = useState(0.55);

  useEffect(() => {
    setPicked(new Set(sources.map((s) => s.key)));
  }, [sources]);

  const toggle = (key: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  return (
    <div className="space-y-4 text-[13px]">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
          Sources
        </p>
        {sources.length === 0 ? (
          <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">
            No footage in this case yet. Recover channels from a device image, or
            add captured / imported clips, then return here.
          </p>
        ) : (
          <ul className="mt-1.5 divide-y divide-[var(--border-subtle)] rounded-md border border-[var(--border-subtle)]">
            {sources.map((s) => (
              <li key={s.key}>
                <label className="flex cursor-pointer items-center gap-2.5 px-2.5 py-2 hover:bg-[var(--surface-2)]">
                  <input
                    type="checkbox"
                    checked={picked.has(s.key)}
                    onChange={() => toggle(s.key)}
                  />
                  <span className="flex-1 truncate font-medium text-[var(--text-primary)]">
                    {s.label}
                  </span>
                  <span className="shrink-0 text-[10px] text-[var(--text-tertiary)]">
                    {s.kind === "recovered_channel"
                      ? `${s.clip_count} clip${s.clip_count === 1 ? "" : "s"}`
                      : "video"}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>

      <label className="block">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">
          Sample rate
        </span>
        <select
          className="mt-1 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-0)] px-2 py-1.5 text-[13px]"
          value={fps}
          onChange={(e) => setFps(Number(e.target.value))}
        >
          {FPS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <span className="mt-1 block text-[11px] text-[var(--text-tertiary)]">
          Lower is faster; higher catches brief appearances.
        </span>
      </label>

      <label className="block">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">
          Match strictness &mdash; {Math.round(sensitivity * 100)}%
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={sensitivity}
          onChange={(e) => setSensitivity(Number(e.target.value))}
          className="mt-2 w-full"
        />
        <span className="mt-1 block text-[11px] text-[var(--text-tertiary)]">
          Higher keeps people apart; lower groups more aggressively.
        </span>
      </label>

      {!models.reid ? (
        <p className="rounded-md border border-[var(--status-warning)]/40 bg-[var(--surface-2)] px-2.5 py-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          Re-identification model not installed on the engine host. Run{" "}
          <code className="mono">
            python scripts/validation/fetch_validation_assets.py
          </code>{" "}
          and reload.
        </p>
      ) : null}

      <Button
        className="w-full"
        disabled={busy || !models.reid || picked.size === 0}
        onClick={() =>
          onRun({
            source_keys: [...picked],
            fps,
            match_sensitivity: sensitivity,
          })
        }
      >
        {busy ? "Correlating…" : "Run correlation"}
      </Button>
    </div>
  );
}

/* --------------------------------------------------------------- timeline */
const TICKS = [0, 0.25, 0.5, 0.75, 1];

function MovementTimeline({
  detail,
  selectedId,
  onPick,
}: {
  detail: CrossCameraIdentityDetail;
  selectedId: string | null;
  onPick: (a: CrossCameraAppearance) => void;
}) {
  const first = detail.first_seen_ms;
  const span = Math.max(1, detail.last_seen_ms - first);

  const lanes = useMemo(() => {
    const byCam = new Map<string, CrossCameraAppearance[]>();
    for (const a of detail.appearances) {
      const arr = byCam.get(a.source_label) ?? [];
      arr.push(a);
      byCam.set(a.source_label, arr);
    }
    return [...byCam.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [detail]);

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] p-4">
      <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
        Movement across cameras
      </p>

      {/* time axis */}
      <div className="mt-3 flex items-end gap-3">
        <span className="w-36 shrink-0" />
        <div className="relative mx-2 h-4 flex-1">
          {TICKS.map((f) => (
            <span
              key={f}
              className="absolute top-0 -translate-x-1/2 text-[10px] tabular-nums text-[var(--text-tertiary)]"
              style={{ left: `${f * 100}%` }}
            >
              {fmtClock(first + f * span)}
            </span>
          ))}
        </div>
      </div>

      {/* lanes */}
      <div className="mt-1 space-y-2">
        {lanes.map(([cam, aps]) => (
          <div key={cam} className="flex items-center gap-3">
            <span
              className="w-36 shrink-0 truncate text-[12px] text-[var(--text-secondary)]"
              title={cam}
            >
              {cam}
            </span>
            <div className="relative mx-2 h-9 flex-1 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)]">
              {TICKS.slice(1, -1).map((f) => (
                <span
                  key={f}
                  className="absolute inset-y-0 w-px bg-[var(--border-subtle)]"
                  style={{ left: `${f * 100}%` }}
                />
              ))}
              {aps.map((a) => {
                const active = selectedId === a.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    title={`${cam} · ${fmtClock(a.offset_ms)} · detection ${a.confidence.toFixed(2)}`}
                    onClick={() => onPick(a)}
                    className={`absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border transition-colors ${
                      active
                        ? "z-10 border-[var(--accent-600)] bg-[var(--accent-500)] ring-2 ring-[var(--accent-500)]/30"
                        : "border-[var(--accent-600)]/40 bg-[var(--accent-500)]/60 hover:bg-[var(--accent-500)]"
                    }`}
                    style={{ left: `${((a.offset_ms - first) / span) * 100}%` }}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <p className="mt-3 text-[11px] text-[var(--text-tertiary)]">
        Each dot is one detection. Click one to open the frame and save it as
        evidence.
      </p>
    </div>
  );
}

/* -------------------------------------------------------- frame inspector */
function FrameInspector({
  appearance,
  actor,
}: {
  appearance: CrossCameraAppearance;
  actor: string;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    setSaved(null);
  }, [appearance.id]);

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
          Frame
        </p>
        <Button
          size="sm"
          variant="secondary"
          disabled={saving || !!saved}
          onClick={async () => {
            setSaving(true);
            try {
              const r = await api.crossCameraSaveStill(appearance.id, actor);
              setSaved(r.sha256);
              toast.success("Still saved to evidence", {
                description: `sha256 ${r.sha256.slice(0, 16)}…`,
              });
            } catch (e) {
              toast.error(
                e instanceof Error ? e.message : "Could not save still",
              );
            } finally {
              setSaving(false);
            }
          }}
        >
          {saved ? "Saved" : saving ? "Saving…" : "Save as evidence"}
        </Button>
      </div>
      <img
        alt="detection frame"
        className="mt-2 w-full rounded border border-[var(--border-subtle)] bg-black object-contain"
        src={api.crossCameraCropUrl(appearance.id, true)}
      />
      <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
        {appearance.source_label} &middot; {fmtClock(appearance.offset_ms)}{" "}
        <span className="text-[var(--text-tertiary)]">
          (detection {appearance.confidence.toFixed(2)})
        </span>
      </p>
      {saved ? (
        <p className="mono mt-1 break-all text-[10px] text-[var(--text-tertiary)]">
          sha256:{saved}
        </p>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- find tab */
function FindPanel({
  runId,
  actor,
  models,
}: {
  runId: string;
  actor: string;
  models: Models;
}) {
  const [mode, setMode] = useState<"appearance" | "face">("appearance");
  const [result, setResult] = useState<CrossCameraSearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [queryUrl, setQueryUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function run(file: File) {
    setBusy(true);
    setResult(null);
    setQueryUrl(URL.createObjectURL(file));
    try {
      const r = await api.crossCameraSearch(runId, file, mode);
      setResult(r);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="inline-flex overflow-hidden rounded-md border border-[var(--border-subtle)] text-[12px]">
          {(["appearance", "face"] as const).map((m) => (
            <button
              key={m}
              type="button"
              disabled={m === "face" && !models.face}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 font-medium disabled:cursor-not-allowed disabled:opacity-40 ${
                mode === m
                  ? "bg-[var(--accent-500)] text-white"
                  : "bg-[var(--surface-0)] text-[var(--text-secondary)] hover:bg-[var(--surface-2)]"
              }`}
              title={
                m === "face" && !models.face
                  ? "Face models not installed on the engine host"
                  : undefined
              }
            >
              {m === "appearance" ? "Appearance" : "Face"}
            </button>
          ))}
        </div>
        <p className="max-w-md text-[11px] leading-relaxed text-[var(--text-tertiary)]">
          {mode === "appearance"
            ? "Matches clothing and body shape. Works at normal surveillance distance."
            : "Matches only frames where the person's face is large and roughly front-facing — uncommon on wide-angle CCTV."}
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void run(f);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer items-center gap-4 rounded-lg border border-dashed px-4 py-5 text-[13px] transition-colors ${
          dragOver
            ? "border-[var(--accent-500)] bg-[var(--accent-500)]/5"
            : "border-[var(--border-subtle)] hover:border-[var(--accent-500)]/50"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void run(f);
          }}
        />
        {queryUrl ? (
          <img
            alt="reference"
            src={queryUrl}
            className="h-20 w-16 shrink-0 rounded border border-[var(--border-subtle)] object-cover"
          />
        ) : (
          <div className="grid h-20 w-16 shrink-0 place-items-center rounded border border-[var(--border-subtle)] bg-[var(--surface-2)] text-[10px] text-[var(--text-tertiary)]">
            no image
          </div>
        )}
        <div>
          <p className="font-medium text-[var(--text-primary)]">
            {busy
              ? "Searching…"
              : queryUrl
                ? "Drop another photo or click to replace"
                : "Drop a reference photo here, or click to choose"}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">
            One clear photo of a single person. Ranked appearances come back with
            camera and timestamp.
          </p>
        </div>
      </div>

      {result ? (
        <>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Compared against {result.appearances_comparable} of{" "}
            {result.appearances_total} appearances
            {mode === "face" && result.appearances_comparable === 0
              ? " — no appearance in this run had a usable face."
              : "."}
          </p>
          {result.matches.length === 0 ? (
            <p className="text-[13px] text-[var(--text-secondary)]">
              No appearances matched the reference photo.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {result.matches.map((m: CrossCameraMatch) => (
                <div
                  key={m.appearance_id}
                  className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)]"
                >
                  <img
                    alt="match"
                    className="aspect-[3/4] w-full bg-[var(--surface-3)] object-cover"
                    src={api.crossCameraCropUrl(m.appearance_id)}
                  />
                  <div className="space-y-1 p-2 text-[11px]">
                    <p className="truncate font-medium text-[var(--text-primary)]">
                      {m.source_label}
                    </p>
                    <p className="text-[var(--text-tertiary)]">
                      {fmtClock(m.offset_ms)} &middot; {m.identity_label}
                    </p>
                    <div className="h-1 rounded-full bg-[var(--surface-3)]">
                      <div
                        className="h-full rounded-full bg-[var(--accent-500)]"
                        style={{
                          width: `${Math.max(4, Math.min(100, m.similarity * 100))}%`,
                        }}
                      />
                    </div>
                    <p className="text-[var(--text-tertiary)]">
                      similarity {m.similarity.toFixed(2)}
                    </p>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 px-1 text-[10px]"
                      onClick={async () => {
                        try {
                          const r = await api.crossCameraSaveStill(
                            m.appearance_id,
                            actor,
                          );
                          toast.success("Still saved to evidence", {
                            description: `sha256 ${r.sha256.slice(0, 16)}…`,
                          });
                        } catch (e) {
                          toast.error(
                            e instanceof Error ? e.message : "Could not save",
                          );
                        }
                      }}
                    >
                      Save as evidence
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------------- page */
export function CaseCrossCameraPage() {
  const { caseId, workspace } = useCaseContext();
  const actor = workspace?.case?.examiner_name || "Examiner";

  const [sources, setSources] = useState<CrossCameraSource[]>([]);
  const [models, setModels] = useState<Models>({
    detector: true,
    reid: true,
    face: false,
  });
  const [runs, setRuns] = useState<CrossCameraRun[]>([]);
  const [activeRun, setActiveRun] = useState<CrossCameraRunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"trace" | "find">("trace");
  const [setupOpen, setSetupOpen] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CrossCameraIdentityDetail | null>(null);
  const [selectedApp, setSelectedApp] = useState<CrossCameraAppearance | null>(
    null,
  );

  const refresh = useCallback(async () => {
    const [src, runList] = await Promise.all([
      api.crossCameraSources(caseId),
      api.crossCameraRuns(caseId),
    ]);
    setSources(src.sources);
    setModels(src.models);
    setRuns(runList.runs);
    const done = runList.runs.find((r) => r.status === "completed");
    if (done && !activeRun) {
      setActiveRun(await api.crossCameraRun(done.id));
    }
  }, [caseId, activeRun]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setSelectedApp(null);
      return;
    }
    let alive = true;
    setDetail(null);
    setSelectedApp(null);
    void api.crossCameraIdentity(selectedId).then((d) => {
      if (!alive) return;
      setDetail(d);
      setSelectedApp(d.appearances[0] ?? null);
    });
    return () => {
      alive = false;
    };
  }, [selectedId]);

  async function startRun(opts: {
    source_keys: string[];
    fps: number;
    match_sensitivity: number;
  }) {
    setBusy(true);
    setSelectedId(null);
    try {
      const { run_id, job_id } = await api.startCrossCameraRun(caseId, {
        actor,
        ...opts,
      });
      await new Promise<void>((resolve, reject) => {
        subscribeJobEvents(job_id, {
          onEvent: (e) => {
            if (e.message) toast.message(e.message, { id: "ccam-progress" });
            if (e.status === "completed") resolve();
            if (e.status === "failed")
              reject(new Error(e.error ?? "Correlation failed"));
          },
          onError: reject,
        });
      });
      toast.dismiss("ccam-progress");
      const d = await api.crossCameraRun(run_id);
      setActiveRun(d);
      setSetupOpen(false);
      setTab("trace");
      const [src, runList] = await Promise.all([
        api.crossCameraSources(caseId),
        api.crossCameraRuns(caseId),
      ]);
      setSources(src.sources);
      setModels(src.models);
      setRuns(runList.runs);
      toast.success(
        `${d.summary.identities ?? 0} people, ${d.summary.cross_camera_identities ?? 0} on 2+ cameras`,
      );
    } catch (e) {
      toast.dismiss("ccam-progress");
      toast.error(e instanceof Error ? e.message : "Correlation failed", {
        duration: Infinity,
      });
    } finally {
      setBusy(false);
    }
  }

  const sum = activeRun?.summary;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        kicker="Correlation"
        title="Cross-camera trace"
        subtitle="Find the same person across every recovered channel and imported clip in this case. One offline batch pass over footage already held as evidence."
      />

      <div className="flex min-h-0 flex-1">
        {/* ---- left rail ---- */}
        <aside className="flex w-[320px] shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-1)]">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
            <p className="text-[13px] font-semibold text-[var(--text-primary)]">
              {activeRun ? "People" : "New correlation"}
            </p>
            {activeRun ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setSetupOpen((v) => !v)}
              >
                {setupOpen ? "Cancel" : "New run"}
              </Button>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {setupOpen || !activeRun ? (
              <div className="border-b border-[var(--border-subtle)] p-4">
                <SetupSection
                  sources={sources}
                  models={models}
                  busy={busy}
                  onRun={startRun}
                />
                {runs.length > 0 ? (
                  <div className="mt-5">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
                      Earlier runs
                    </p>
                    <ul className="mt-1.5 space-y-1 text-[12px]">
                      {runs.map((r) => (
                        <li key={r.id}>
                          <button
                            type="button"
                            className="text-left text-[var(--accent-600)] underline disabled:no-underline disabled:opacity-60"
                            disabled={r.status !== "completed"}
                            onClick={async () => {
                              setActiveRun(await api.crossCameraRun(r.id));
                              setSetupOpen(false);
                              setSelectedId(null);
                            }}
                          >
                            {new Date(r.created_at).toLocaleString()} &middot;{" "}
                            {r.status === "completed"
                              ? `${r.summary.identities ?? 0} people`
                              : r.status}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}

            {activeRun && !setupOpen ? (
              <ul className="p-2">
                {activeRun.identities.length === 0 ? (
                  <li className="px-2 py-3 text-[12px] text-[var(--text-secondary)]">
                    No people were tracked in the selected sources.
                  </li>
                ) : (
                  activeRun.identities.map((it) => {
                    const active = selectedId === it.id;
                    return (
                      <li key={it.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(it.id)}
                          className={`flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors ${
                            active
                              ? "bg-[var(--accent-500)]/10 ring-1 ring-[var(--accent-500)]/40"
                              : "hover:bg-[var(--surface-2)]"
                          }`}
                        >
                          <img
                            alt={it.label}
                            className="h-14 w-11 shrink-0 rounded border border-[var(--border-subtle)] object-cover"
                            src={api.crossCameraIdentityThumbUrl(it.id)}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-semibold text-[var(--text-primary)]">
                              {it.label}
                            </p>
                            <p className="truncate text-[11px] text-[var(--text-secondary)]">
                              {it.camera_count} camera
                              {it.camera_count === 1 ? "" : "s"} &middot;{" "}
                              {it.appearance_count} seen
                            </p>
                            <p className="text-[10px] tabular-nums text-[var(--text-tertiary)]">
                              {fmtClock(it.first_seen_ms)}&ndash;
                              {fmtClock(it.last_seen_ms)}
                            </p>
                          </div>
                          {it.camera_count >= 2 ? (
                            <span className="shrink-0 rounded-full bg-[var(--accent-500)]/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-[var(--accent-600)]">
                              2+
                            </span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
            ) : null}
          </div>
        </aside>

        {/* ---- main pane ---- */}
        <div className="flex min-h-0 flex-1 flex-col">
          {activeRun ? (
            <>
              <div className="flex items-center gap-4 border-b border-[var(--border-subtle)] px-5">
                {(["trace", "find"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTab(t)}
                    className={`-mb-px border-b-2 py-3 text-[13px] font-medium ${
                      tab === t
                        ? "border-[var(--accent-500)] text-[var(--text-primary)]"
                        : "border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                    }`}
                  >
                    {t === "trace" ? "Trace" : "Find a person"}
                  </button>
                ))}
                <span className="ml-auto py-3 text-[12px] tabular-nums text-[var(--text-tertiary)]">
                  {sum?.identities ?? 0} people &middot;{" "}
                  {sum?.cross_camera_identities ?? 0} on 2+ cameras &middot;{" "}
                  {sum?.detections ?? 0} detections
                  {typeof sum?.appearances_with_face === "number"
                    ? ` · ${sum.appearances_with_face} with a face`
                    : ""}
                </span>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto p-5">
                {tab === "trace" ? (
                  !selectedId ? (
                    <div className="grid h-full place-items-center text-center">
                      <p className="max-w-sm text-[13px] text-[var(--text-secondary)]">
                        Select a person on the left to see which cameras saw them
                        and when.
                      </p>
                    </div>
                  ) : !detail ? (
                    <p className="text-[13px] text-[var(--text-tertiary)]">
                      Loading…
                    </p>
                  ) : (
                    <div className="space-y-4">
                      <div className="flex gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-0)] p-4">
                        <img
                          alt={detail.label}
                          className="h-28 w-20 shrink-0 rounded border border-[var(--border-subtle)] object-cover"
                          src={api.crossCameraIdentityThumbUrl(detail.id)}
                        />
                        <div className="min-w-0">
                          <p className="text-[16px] font-semibold text-[var(--text-primary)]">
                            {detail.label}
                          </p>
                          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                            Seen on{" "}
                            {Object.entries(detail.cameras)
                              .map(([name, c]) => `${name} (${c.count}×)`)
                              .join(", ")}
                          </p>
                          <p className="mt-0.5 text-[12px] tabular-nums text-[var(--text-tertiary)]">
                            {fmtClock(detail.first_seen_ms)} &rarr;{" "}
                            {fmtClock(detail.last_seen_ms)} &middot;{" "}
                            {detail.appearance_count} detections across{" "}
                            {detail.camera_count} camera
                            {detail.camera_count === 1 ? "" : "s"}
                          </p>
                        </div>
                      </div>

                      <MovementTimeline
                        detail={detail}
                        selectedId={selectedApp?.id ?? null}
                        onPick={setSelectedApp}
                      />

                      {selectedApp ? (
                        <FrameInspector
                          appearance={selectedApp}
                          actor={actor}
                        />
                      ) : null}
                    </div>
                  )
                ) : (
                  <FindPanel
                    runId={activeRun.id}
                    actor={actor}
                    models={models}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="grid h-full place-items-center p-8 text-center">
              <p className="max-w-sm text-[13px] text-[var(--text-secondary)]">
                Pick the footage to correlate on the left and run a pass. The
                result is a list of people with the cameras and times that saw
                each one.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
