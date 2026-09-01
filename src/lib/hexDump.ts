export function formatHexDump(
  hex: string,
  ascii: string,
  offset: number,
  bytesPerRow = 16,
): string {
  const bytes = hex.match(/.{1,2}/g) ?? [];
  const lines: string[] = [];
  for (let i = 0; i < bytes.length; i += bytesPerRow) {
    const slice = bytes.slice(i, i + bytesPerRow);
    const addr = (offset + i).toString(16).padStart(8, "0");
    const hexPart = slice
      .map((b) => b.toUpperCase())
      .join(" ")
      .padEnd(bytesPerRow * 3 - 1, " ");
    const asciiPart = ascii.slice(i, i + bytesPerRow);
    lines.push(`${addr}  ${hexPart}  ${asciiPart}`);
  }
  return lines.join("\n");
}
