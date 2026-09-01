import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import type { ChainLinkState } from "@/components/forensic/ChainLinkIndicator";

export function StatusBar() {
  const [online, setOnline] = useState<boolean | null>(null);
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
          await api.version();
          if (!cancelled) setOnline(true);
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
    const timer = window.setInterval(() => void checkEngine(), 15_000);
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
    void api
      .getCase(caseId)
      .then((w) => setCaseName(w.case.name))
      .catch(() => setCaseName(null));
    void api
      .custodyStatus(caseId)
      .then((s) => setCustody(s.intact ? "intact" : "broken"))
      .catch(() => setCustody("unknown"));
  }, [caseId, location.pathname]);

  useEffect(() => {
    const tick = () =>
      setTime(
        new Date().toLocaleString(undefined, {
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        }),
      );
    tick();
    const id = window.setInterval(tick, 30_000);
    return () => window.clearInterval(id);
  }, []);

  const custodyLabel =
    custody === "intact"
      ? "Custody verified"
      : custody === "broken"
        ? "Custody broken"
        : custody === "checking"
          ? null
          : null;

  return (
    <footer id="tour-status" className="status-footer">
      <div className="flex min-w-0 items-center gap-3 text-[11px]">
        {online === false ? (
          <span className="font-medium text-[var(--status-danger)]">
            Engine not running — start Pramaan or run python run.py
          </span>
        ) : caseName ? (
          <>
            <span className="truncate font-medium text-[var(--text-secondary)]">
              {caseName}
            </span>
            {custodyLabel ? (
              <span
                className={
                  custody === "broken"
                    ? "text-[var(--status-danger)]"
                    : "text-[var(--text-tertiary)]"
                }
              >
                {custodyLabel}
              </span>
            ) : null}
          </>
        ) : null}
      </div>
      {time ? (
        <span className="shrink-0 tabular-nums text-[var(--text-tertiary)]">
          {time}
        </span>
      ) : null}
    </footer>
  );
}

function extractCaseId(pathname: string): string | null {
  const match = pathname.match(/^\/cases\/([^/]+)/);
  return match ? match[1] : null;
}
