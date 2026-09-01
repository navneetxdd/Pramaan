type VideoPreviewProps = {
  src: string;
  mediaType?: string;
};

function transcodeUrl(src: string): string {
  const separator = src.includes("?") ? "&" : "?";
  return `${src}${separator}transcode=1`;
}

export function VideoPreview({ src, mediaType }: VideoPreviewProps) {
  const isRawH264 =
    mediaType === "h264" ||
    mediaType === "application/octet-stream" ||
    mediaType === "video/H264" ||
    src.endsWith(".h264");

  if (isRawH264) {
    return (
      <div className="space-y-2">
        <div
          className="overflow-hidden rounded border"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <video
            className="w-full bg-black"
            src={transcodeUrl(src)}
            controls
            preload="metadata"
            onError={(event) => {
              const target = event.currentTarget;
              target.style.display = "none";
              const fallback = target.nextElementSibling;
              if (fallback instanceof HTMLElement) {
                fallback.hidden = false;
              }
            }}
          >
            <track kind="captions" />
          </video>
          <div hidden className="rounded border p-4 text-[13px]" style={{ borderColor: "var(--border-subtle)", background: "var(--surface-4)", color: "var(--text-secondary)" }}>
            Inline playback needs FFmpeg on the engine host.
            <a className="btn-secondary mt-3 inline-flex" href={src} download>
              Download raw H.264
            </a>
          </div>
        </div>
        <p className="text-[11px] text-[var(--text-tertiary)]">
          Attempting inline MP4 remux via engine FFmpeg. If playback fails, download the raw stream.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded border" style={{ borderColor: "var(--border-subtle)" }}>
      <video className="w-full bg-black" src={src} controls preload="metadata">
        <track kind="captions" />
      </video>
    </div>
  );
}
