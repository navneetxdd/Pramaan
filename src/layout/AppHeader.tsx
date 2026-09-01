import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ChevronDown, Lock, Shield, Activity, Database } from "lucide-react";
import { useActivity } from "@/context/ActivityContext";
import { useBreadcrumb } from "./ModuleSidebar";
import { api, type CaseRecord } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";
import { runningJobs } from "@/lib/caseStats";
import type { ChainLinkState } from "@/components/forensic/ChainLinkIndicator";

export function AppHeader() {
  const { mode, message } = useActivity();
  const { page } = useBreadcrumb();
  const { caseId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [activeCase, setActiveCase] = useState<CaseRecord | null>(null);
  const [liveProgress, setLiveProgress] = useState<number | null>(null);
  const [storageBytes, setStorageBytes] = useState(0);
  const [custodyState, setCustodyState] = useState<ChainLinkState>("unknown");

  useEffect(() => {
    void api
      .listCaseRegistry()
      .then(setCases)
      .catch(() => setCases([]));
  }, [location.pathname]);

  useEffect(() => {
    if (!caseId) {
      setActiveCase(null);
      setLiveProgress(null);
      setStorageBytes(0);
      setCustodyState("unknown");
      return;
    }
    void api
      .getCase(caseId)
      .then((w) => {
        setActiveCase(w.case);
        setStorageBytes(w.evidence.reduce((s, e) => s + e.size_bytes, 0));
      })
      .catch(() => {
        setActiveCase(null);
        setStorageBytes(0);
      });
    setCustodyState("checking");
    void api
      .custodyStatus(caseId)
      .then((s) => setCustodyState(s.intact ? "intact" : "broken"))
      .catch(() => setCustodyState("unknown"));
  }, [caseId, location.pathname]);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    async function poll() {
      try {
        const w = await api.getCase(caseId!);
        const active = runningJobs(w.jobs)[0];
        if (!active) {
          if (!cancelled) setLiveProgress(null);
          return;
        }
        const status = await api.getJobStatus(active.id);
        if (!cancelled && typeof status.progress === "number")
          setLiveProgress(Math.round(status.progress));
      } catch {
        if (!cancelled) setLiveProgress(null);
      }
    }
    void poll();
    const timer = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [caseId, location.pathname]);

  return (
    <header
      className="relative shrink-0 border-b bg-white px-4 py-2"
      style={{ borderColor: "var(--border-subtle)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {caseId && activeCase ? (
            <div className="relative">
              <select
                className="field mono max-w-[340px] appearance-none border-[var(--border-subtle)] bg-white pr-8 text-[11px] font-semibold uppercase"
                value={caseId}
                onChange={(e) => navigate(`/cases/${e.target.value}`)}
              >
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name.slice(0, 40)} — {c.examiner_name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-tertiary)]" />
            </div>
          ) : (
            <Link
              to="/cases"
              className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              Cases
            </Link>
          )}
          <span className="hidden text-[var(--text-tertiary)] sm:inline">
            |
          </span>
          <span className="hidden text-[11px] text-[var(--text-secondary)] sm:inline">
            Workspace:{" "}
            <span className="font-semibold uppercase text-[var(--text-primary)]">
              {page}
            </span>
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {caseId ? (
            <>
              <span className="visily-pill hidden md:inline-flex">
                <Database className="h-3 w-3 text-[var(--status-success)]" />
                {formatBytes(storageBytes)} evidence
              </span>
              {liveProgress !== null ? (
                <span className="visily-pill">
                  <Activity className="h-3 w-3 text-[var(--accent-500)]" />
                  Job {liveProgress}%
                </span>
              ) : null}
              <span
                className={cn(
                  "visily-pill hidden lg:inline-flex",
                  custodyState === "broken" &&
                    "border-[var(--status-danger)] text-[var(--status-danger)]",
                )}
              >
                <Shield
                  className="h-3 w-3"
                  style={{
                    color:
                      custodyState === "intact"
                        ? "var(--status-success)"
                        : custodyState === "broken"
                          ? "var(--status-danger)"
                          : "var(--text-tertiary)",
                  }}
                />
                {custodyState === "intact"
                  ? "Custody verified"
                  : custodyState === "broken"
                    ? "Custody broken"
                    : custodyState === "checking"
                      ? "Checking custody…"
                      : "Custody unknown"}
              </span>
              <span
                className="visily-pill hidden xl:inline-flex"
                title="Engine opens sources read-only; writes go to case storage only"
              >
                <Lock className="h-3 w-3" />
                Read-only imaging
              </span>
            </>
          ) : null}
          <div
            className={cn(
              "hidden rounded-full border px-2.5 py-1 font-mono text-[10px] xl:block",
              mode === "error"
                ? "border-[var(--status-danger)] text-[var(--status-danger)]"
                : "border-[var(--border-subtle)] text-[var(--text-tertiary)]",
            )}
          >
            {message ?? "Local engine"}
          </div>
        </div>
      </div>
      {mode === "working" ? (
        <div className="progress-strip absolute inset-x-0 bottom-0" />
      ) : null}
      {mode === "success" ? (
        <div className="progress-strip progress-strip-success absolute inset-x-0 bottom-0" />
      ) : null}
    </header>
  );
}
