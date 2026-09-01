import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { api } from "@/lib/api";
import { formatHexDump } from "@/lib/hexDump";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type HexViewerProps = {
  deviceId: string;
  baseOffset: number;
  pageSize?: number;
  title?: string;
};

export function HexViewer({
  deviceId,
  baseOffset,
  pageSize = 256,
  title = "Hex view",
}: HexViewerProps) {
  const [offset, setOffset] = useState(baseOffset);
  const [dump, setDump] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState(0);
  const [loading, setLoading] = useState(false);
  const [encoding, setEncoding] = useState<"ascii" | "hex">("ascii");
  const [findQuery, setFindQuery] = useState("");
  const [jumpInput, setJumpInput] = useState("");

  useEffect(() => {
    setOffset(baseOffset);
  }, [baseOffset, deviceId]);

  const loadPage = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try {
      const data = await api.readDeviceBytes(deviceId, offset, pageSize);
      setFileSize(data.file_size);
      setDump(formatHexDump(data.hex, data.ascii, data.offset));
    } catch {
      setDump(null);
    } finally {
      setLoading(false);
    }
  }, [deviceId, offset, pageSize]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  async function handleFind() {
    if (!findQuery.trim()) return;
    try {
      const result = await api.findDeviceBytes(
        deviceId,
        findQuery.trim(),
        offset,
        encoding,
      );
      if (result.offset != null) {
        setOffset(result.offset);
        setJumpInput(`0x${result.offset.toString(16)}`);
      }
    } catch {
      /* toast handled by caller if needed */
    }
  }

  function handleJump() {
    const raw = jumpInput.trim().replace(/^0x/i, "");
    const parsed = Number.parseInt(raw, 16);
    if (!Number.isNaN(parsed) && parsed >= 0) {
      setOffset(parsed);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="visily-card-title text-[11px]">{title}</span>
        <div className="ml-auto flex flex-wrap items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            disabled={offset <= 0}
            onClick={() => setOffset((o) => Math.max(0, o - pageSize))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            disabled={offset + pageSize >= fileSize}
            onClick={() => setOffset((o) => o + pageSize)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Input
          className="field mono max-w-[140px] text-[11px]"
          placeholder="Jump 0x…"
          value={jumpInput}
          onChange={(e) => setJumpInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleJump()}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={handleJump}
        >
          Go
        </Button>
        <select
          className="field text-[11px]"
          value={encoding}
          onChange={(e) => setEncoding(e.target.value as "ascii" | "hex")}
        >
          <option value="ascii">ASCII</option>
          <option value="hex">Hex</option>
        </select>
        <Input
          className="field mono min-w-[120px] flex-1 text-[11px]"
          placeholder="Find string"
          value={findQuery}
          onChange={(e) => setFindQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void handleFind()}
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void handleFind()}
        >
          <Search className="h-3.5 w-3.5" />
          Find
        </Button>
      </div>
      <p className="mono text-[10px] text-[var(--text-tertiary)]">
        Offset {offset} · file {fileSize} bytes
      </p>
      <pre className="max-h-[320px] overflow-auto rounded border border-[var(--border-subtle)] bg-[var(--surface-3)] p-2 font-mono text-[11px] leading-relaxed text-[var(--text-primary)]">
        {loading ? "Loading…" : (dump ?? "Unable to read bytes.")}
      </pre>
    </div>
  );
}
