import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Camera, Grid2X2, Plus, Radio } from "lucide-react";
import { useCaseContext } from "@/context/CaseContext";
import { PageHeader } from "@/components/visily/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type LiveDeviceRecord } from "@/lib/api";
import { shortHash } from "@/lib/utils";
import { resolveApiUrl } from "@/lib/apiBase";
import { toast } from "sonner";

type GridSize = 1 | 4 | 9 | 16;

export function CaseLiveDevicesPage() {
  const { caseId, workspace } = useCaseContext();
  const [devices, setDevices] = useState<LiveDeviceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [gateBlocked, setGateBlocked] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [focused, setFocused] = useState<{
    deviceId: string;
    channel: number;
  } | null>(null);
  const [gridSize, setGridSize] = useState<GridSize>(4);
  const [form, setForm] = useState({
    display_name: "",
    vendor: "generic_rtsp" as LiveDeviceRecord["vendor"],
    host: "127.0.0.1",
    port: "8554",
    scheme: "http",
    user: "",
    password: "",
    rtsp_url_override: "rtsp://127.0.0.1:8554/cam1",
    authorized: false,
  });
  const [probeResult, setProbeResult] = useState<string | null>(null);

  const actor = workspace?.case?.examiner_name || "Examiner";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.listLiveDevices(caseId);
      setDevices(response.devices);
      setGateBlocked(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        message.includes("403") ||
        message.toLowerCase().includes("logical_acquire")
      ) {
        setGateBlocked(true);
      }
      setDevices([]);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeDevice = useMemo(
    () => devices.find((d) => d.id === focused?.deviceId) ?? devices[0],
    [devices, focused],
  );

  const channels = activeDevice?.channels ?? [];
  const visibleChannels = channels.slice(0, gridSize);

  async function testConnection() {
    if (!form.authorized) {
      setProbeResult("Confirm lawful authorisation before connecting.");
      return;
    }
    setProbeResult("Probing…");
    try {
      const created = await api.addLiveDevice(caseId, {
        actor: actor,
        display_name: form.display_name || "Live device",
        vendor: form.vendor,
        host: form.host,
        port: Number(form.port) || 554,
        scheme: form.scheme,
        user: form.user,
        password: form.password,
        rtsp_url_override:
          form.vendor === "generic_rtsp" ? form.rtsp_url_override : undefined,
      });
      setProbeResult(`Connected — ${created.channels.length} channel(s)`);
      setDialogOpen(false);
      await refresh();
    } catch (error) {
      setProbeResult(error instanceof Error ? error.message : String(error));
    }
  }

  async function captureSnapshot(deviceId: string, channel: number) {
    try {
      const result = await api.liveSnapshot(deviceId, {
        actor: actor,
        channel,
      });
      toast.success(`Snapshot ${shortHash(result.sha256)}`, {
        description: (
          <Link className="underline" to={`/cases/${caseId}/custody`}>
            View custody log
          </Link>
        ),
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Snapshot failed");
    }
  }

  async function captureClip(deviceId: string, channel: number, duration = 30) {
    try {
      const result = await api.liveCapture(deviceId, {
        actor: actor,
        channel,
        duration_s: duration,
      });
      toast.success(`Captured ${shortHash(result.evidence.sha256)}`, {
        description: (
          <Link className="underline" to={`/cases/${caseId}/evidence`}>
            Evidence catalog
          </Link>
        ),
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Capture failed");
    }
  }

  if (gateBlocked) {
    return (
      <div>
        <PageHeader
          kicker="Live devices"
          title="Network live preview disabled"
          subtitle="Set PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1 on the engine host to connect to powered NVRs and IP cameras on the examination LAN."
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        kicker="Live devices"
        title="Connected cameras & NVR channels"
        subtitle="Forensic live preview bound to this case. Snapshots and captures are hash-sealed into custody."
        actions={
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Add device
          </Button>
        }
      />

      <div className="flex min-h-0 flex-1">
        <aside className="w-64 shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-tertiary)]">
            Connected devices
          </p>
          <ul className="mt-3 space-y-2">
            {devices.map((device) => (
              <li key={device.id}>
                <button
                  type="button"
                  className={`w-full rounded-lg border px-3 py-2 text-left text-[12px] ${
                    activeDevice?.id === device.id
                      ? "border-[var(--accent-500)] bg-[var(--surface-0)]"
                      : "border-[var(--border-subtle)] bg-[var(--surface-2)]"
                  }`}
                  onClick={() =>
                    setFocused({ deviceId: device.id, channel: 1 })
                  }
                >
                  <p className="font-semibold text-[var(--text-primary)]">
                    {device.display_name}
                  </p>
                  <p className="text-[10px] text-[var(--text-tertiary)]">
                    {device.vendor} · {device.channel_count} ch
                  </p>
                </button>
              </li>
            ))}
            {!loading && devices.length === 0 ? (
              <li className="text-[12px] text-[var(--text-tertiary)]">
                No devices connected.
              </li>
            ) : null}
          </ul>
        </aside>

        <main className="min-w-0 flex-1 p-4">
          {focused && activeDevice ? (
            <div className="mb-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setFocused(null)}
              >
                Back to grid
              </Button>
              <video
                className="mt-3 max-h-[70vh] w-full rounded-lg border border-[var(--border-subtle)] bg-black"
                src={api.liveMp4Url(activeDevice.id, focused.channel)}
                autoPlay
                muted
                playsInline
                controls
              />
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  onClick={() =>
                    void captureSnapshot(activeDevice.id, focused.channel)
                  }
                >
                  Snapshot
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    void captureClip(activeDevice.id, focused.channel, 30)
                  }
                >
                  Record 30s
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    void captureClip(activeDevice.id, focused.channel, 60)
                  }
                >
                  Capture 60s
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="mb-3 flex items-center gap-2">
                <Grid2X2 className="h-4 w-4 text-[var(--text-tertiary)]" />
                {[1, 4, 9, 16].map((size) => (
                  <Button
                    key={size}
                    size="sm"
                    variant={gridSize === size ? "default" : "secondary"}
                    onClick={() => setGridSize(size as GridSize)}
                  >
                    {size}
                  </Button>
                ))}
              </div>
              <div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: `repeat(${Math.ceil(Math.sqrt(gridSize))}, minmax(0, 1fr))`,
                }}
              >
                {activeDevice
                  ? visibleChannels.map((channel) => (
                      <div
                        key={channel.channel}
                        className="relative overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]"
                      >
                        <img
                          alt={channel.label}
                          className="aspect-video w-full object-cover"
                          src={api.liveMjpegUrl(
                            activeDevice.id,
                            channel.channel,
                          )}
                        />
                        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/50 px-2 py-1 text-[10px] text-white">
                          <span>{channel.label}</span>
                          <span className="flex items-center gap-1">
                            <Radio className="h-3 w-3 text-emerald-400" />
                            live
                          </span>
                        </div>
                        <div className="flex gap-1 p-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              void captureSnapshot(
                                activeDevice.id,
                                channel.channel,
                              )
                            }
                          >
                            Snapshot
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              void captureClip(activeDevice.id, channel.channel)
                            }
                          >
                            Record 30s
                          </Button>
                          <Button
                            size="sm"
                            onClick={() =>
                              setFocused({
                                deviceId: activeDevice.id,
                                channel: channel.channel,
                              })
                            }
                          >
                            Expand
                          </Button>
                        </div>
                      </div>
                    ))
                  : null}
              </div>
            </>
          )}

          {activeDevice ? (
            <div className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
              <p className="text-[11px] font-semibold text-[var(--text-primary)]">
                Pull recordings from this device
              </p>
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                Use logical acquisition with enumerated channels and a time
                range.
              </p>
              <Link
                className="mt-2 inline-flex text-[12px] font-medium text-[var(--accent-600)] underline"
                to={`/cases/${caseId}/live?pull=${activeDevice.id}`}
              >
                Open recording pull for {activeDevice.display_name}
              </Link>
            </div>
          ) : null}
        </main>
      </div>

      {dialogOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-0)] p-5 shadow-lg">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Add live device
            </h2>
            <div className="mt-4 space-y-2">
              <Input
                placeholder="Display name"
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
              />
              <select
                className="field w-full"
                value={form.vendor}
                onChange={(e) =>
                  setForm({
                    ...form,
                    vendor: e.target.value as LiveDeviceRecord["vendor"],
                  })
                }
              >
                <option value="hikvision">Hikvision ISAPI</option>
                <option value="dahua">Dahua CGI</option>
                <option value="onvif">ONVIF</option>
                <option value="generic_rtsp">Generic RTSP</option>
              </select>
              <Input
                placeholder="Host / IP"
                value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
              />
              <Input
                placeholder="Port"
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
              />
              <Input
                placeholder="Username"
                value={form.user}
                onChange={(e) => setForm({ ...form, user: e.target.value })}
              />
              <Input
                type="password"
                placeholder="Password (session only)"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              {form.vendor === "generic_rtsp" ? (
                <Input
                  placeholder="rtsp://…"
                  value={form.rtsp_url_override}
                  onChange={(e) =>
                    setForm({ ...form, rtsp_url_override: e.target.value })
                  }
                />
              ) : null}
              <label className="flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={form.authorized}
                  onChange={(e) =>
                    setForm({ ...form, authorized: e.target.checked })
                  }
                />
                Only connect to devices I am lawfully authorised to examine.
              </label>
              {probeResult ? (
                <p className="text-[12px] text-[var(--text-secondary)]">
                  {probeResult}
                </p>
              ) : null}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => void testConnection()}>
                <Camera className="h-4 w-4" />
                Test connection
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
