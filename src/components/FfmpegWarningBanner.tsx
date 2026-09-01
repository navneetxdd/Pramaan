import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";

const DISMISS_KEY = "pramaan-ffmpeg-warning-dismissed";

export function FfmpegWarningBanner() {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === "1",
  );
  const [ffmpegMissing, setFfmpegMissing] = useState(false);

  useEffect(() => {
    if (dismissed) {
      return;
    }

    let cancelled = false;
    api
      .version()
      .then((payload) => {
        if (!cancelled && payload.capabilities.ffmpeg_available === false) {
          setFfmpegMissing(true);
        }
      })
      .catch(() => {
        // Engine not ready yet — banner is non-critical.
      });

    return () => {
      cancelled = true;
    };
  }, [dismissed]);

  if (dismissed || !ffmpegMissing) {
    return null;
  }

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
    setFfmpegMissing(false);
  }

  return (
    <div
      className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--status-warning)] bg-amber-50 px-4 py-2 text-[12px] text-amber-950"
      role="status"
    >
      <p>
        <span className="font-semibold">MP4 export unavailable.</span> FFmpeg
        was not found on this workstation. Segment recovery still works; exports
        remain raw H.264 until you install a licensed FFmpeg build and add it to
        PATH, or set{" "}
        <code className="rounded bg-amber-100/80 px-1 py-0.5 font-mono text-[11px]">
          FORENSIC_FFMPEG
        </code>
        .
      </p>
      <button
        type="button"
        onClick={dismiss}
        className="shrink-0 rounded p-1 text-amber-900 transition hover:bg-amber-100"
        aria-label="Dismiss FFmpeg warning"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
