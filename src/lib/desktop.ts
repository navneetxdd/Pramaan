import { getCurrentWindow } from "@tauri-apps/api/window";
import { open } from "@tauri-apps/plugin-dialog";
import { readFile } from "@tauri-apps/plugin-fs";

export function isDesktopApp(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function pickDiskImage(): Promise<File | null> {
  if (!isDesktopApp()) return null;

  const selected = await open({
    multiple: false,
    directory: false,
    filters: [
      { name: "Disk images", extensions: ["bin", "img", "dd", "raw", "001", "e01"] },
      { name: "All files", extensions: ["*"] },
    ],
  });

  if (!selected || Array.isArray(selected)) return null;

  try {
    const bytes = await readFile(selected);
    const name = selected.split(/[/\\]/).pop() ?? "evidence.bin";
    return new File([bytes], name, { type: "application/octet-stream" });
  } catch {
    return null;
  }
}

export async function minimizeWindow() {
  if (!isDesktopApp()) return;
  await getCurrentWindow().minimize();
}

export async function toggleMaximizeWindow() {
  if (!isDesktopApp()) return;
  const win = getCurrentWindow();
  if (await win.isMaximized()) await win.unmaximize();
  else await win.maximize();
}

export async function closeWindow() {
  if (!isDesktopApp()) return;
  await getCurrentWindow().close();
}

export async function startWindowDrag() {
  if (!isDesktopApp()) return;
  await getCurrentWindow().startDragging();
}
