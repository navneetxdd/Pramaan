/** API origin: empty in Vite dev (proxy), engine URL in Tauri/production builds. */
export function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE;
  if (typeof configured === "string" && configured.length > 0) {
    return configured.replace(/\/$/, "");
  }
  if (import.meta.env.DEV) return "";
  return "http://127.0.0.1:8787";
}

/** Prefix relative /api paths for reports, exports, and media preview in Tauri builds. */
export function resolveApiUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const base = getApiBase();
  if (!base) return path;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

export function engineHostLabel(): string {
  const base = getApiBase();
  if (!base) return "127.0.0.1:8787 (via dev proxy)";
  try {
    return new URL(base).host;
  } catch {
    return base;
  }
}
