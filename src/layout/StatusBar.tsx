import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { engineHostLabel } from "@/lib/apiBase";
import { ChainLinkIndicator, type ChainLinkState } from "@/components/forensic/ChainLinkIndicator";

export function StatusBar() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [version, setVersion] = useState("—");
  const [cert, setCert] = useState("—");
  const [time, setTime] = useState("");
  const [custody, setCustody] = useState<ChainLinkState>("unknown");
  const [caseName, setCaseName] = useState<string | null>(null);
  const location = useLocation();
  const params = useParams();
  const caseId = params.caseId ?? extractCaseId(location.pathname);

  useEffect(() => {
    let cancelled = false;

    async function checkEngine() {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const response = await api.version();
          if (!cancelled) {
            setOnline(true);
            setVersion(response.version);
            setCert(response.signing_certificate_fingerprint?.slice(0, 8) ?? "—");
          }
          return;
        } catch {
          if (attempt === 0) {
            await new Promise((resolve) => window.setTimeout(resolve, 500));
          }
        }
      }
      if (!cancelled) setOnline(false);
    }

    void checkEngine();
    const timer = window.setInterval(() => void checkEngine(), 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!caseId) {
      setCustody("unknown");
      setCaseName(null);
      return;
    }
    setCustody("checking");
    void api.getCase(caseId).then((w) => setCaseName(w.case.name)).catch(() => setCaseName(null));
    void api
      .custodyStatus(caseId)
      .then((s) => setCustody(s.intact ? "intact" : "broken"))
      .catch(() => setCustody("unknown"));
  }, [caseId, location.pathname]);

  useEffect(() => {
    const tick = () => setTime(new Date().toISOString().replace("T", " ").slice(0, 19));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <footer id="tour-status" className="status-footer">
      <div className="flex items-center gap-3 text-[12px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background:
                online === null
                  ? "var(--text-tertiary)"
                  : online
                    ? "var(--status-success)"
                    : "var(--status-danger)",
            }}
          />
          {online === null ? "Connecting to engine" : online ? "Engine connected" : "Engine offline"}
        </span>
        <span>·</span>
        <span className="mono">{engineHostLabel()}</span>
        <span>·</span>
        <span className="mono">v{version}</span>
        <span>·</span>
        <span className="mono">cert {cert}</span>
        <span>·</span>
        <span className="flex items-center gap-1.5">
          <ChainLinkIndicator state={custody} />
          {caseName ? `${caseName}` : "No active case"}
        </span>
      </div>
      <span className="mono text-[12px] text-[var(--text-tertiary)]">{time} UTC</span>
    </footer>
  );
}

function extractCaseId(pathname: string): string | null {
  const match = pathname.match(/^\/cases\/([^/]+)/);
  return match ? match[1] : null;
}
