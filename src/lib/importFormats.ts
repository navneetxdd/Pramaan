/** Extensions the acquisition engine normalizes on ingest (see engine OEM_EXTENSIONS). */
export const EVIDENCE_IMAGE_EXTENSIONS = [
  ".bin",
  ".dd",
  ".img",
  ".raw",
  ".e01",
  ".ex01",
  ".001",
  ".dav",
  ".mp4",
  ".avi",
  ".264",
  ".h264",
  ".mkv",
  ".ts",
] as const;

const EVIDENCE_IMAGE_RE =
  /\.(bin|dd|img|raw|e01|ex01|001|dav|mp4|avi|264|h264|mkv|ts)$/i;

export function isEvidenceImageFile(file: File): boolean {
  return EVIDENCE_IMAGE_RE.test(file.name);
}

export function isZipArchive(file: File): boolean {
  return file.name.toLowerCase().endsWith(".zip");
}

export type ImportFileKind = "evidence" | "case_export" | "unknown";

export function classifyImportFile(file: File): ImportFileKind {
  if (isEvidenceImageFile(file)) return "evidence";
  if (isZipArchive(file)) return "case_export";
  return "unknown";
}

export const IMPORT_FILE_ACCEPT = [...EVIDENCE_IMAGE_EXTENSIONS, ".zip"].join(
  ",",
);
