type VideoPreviewProps = {
  src: string;
  mediaType?: string;
};

export function VideoPreview({ src, mediaType }: VideoPreviewProps) {
  if (mediaType === "h264") {
    return (
      <div className="rounded border p-4 text-[13px]" style={{ borderColor: "var(--border-subtle)", background: "var(--surface-4)", color: "var(--text-secondary)" }}>
        Raw H.264 exported. Install FFmpeg on the engine host for in-browser MP4 preview.
        <a className="btn-secondary mt-3 inline-flex" href={src} download>
          Download stream
        </a>
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
