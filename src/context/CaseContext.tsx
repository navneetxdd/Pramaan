import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useParams } from "react-router-dom";
import {
  api,
  type CaseRecord,
  type CustodyEvent,
  type EvidenceRecord,
  type RecoveryJob,
} from "@/lib/api";
import { isNotFound } from "@/lib/apiError";

const WORKSPACE_FETCH_TIMEOUT_MS = 20_000;

type CaseWorkspace = {
  case: CaseRecord;
  evidence: EvidenceRecord[];
  jobs: RecoveryJob[];
  custody: CustodyEvent[];
};

type CaseContextValue = {
  caseId: string;
  workspace: CaseWorkspace | null;
  loading: boolean;
  error: string | null;
  notFound: boolean;
  refresh: (options?: { silent?: boolean }) => Promise<void>;
};

const CaseContext = createContext<CaseContextValue | null>(null);

export function CaseProvider({ children }: { children: ReactNode }) {
  const { caseId = "" } = useParams();
  const [workspace, setWorkspace] = useState<CaseWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const workspaceRef = useRef<CaseWorkspace | null>(null);
  const caseIdRef = useRef(caseId);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    workspaceRef.current = workspace;
  }, [workspace]);

  useEffect(() => {
    caseIdRef.current = caseId;
  }, [caseId]);

  const refresh = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!caseId) return;

      abortRef.current?.abort();
      const requestAbort = new AbortController();
      abortRef.current = requestAbort;

      let timedOut = false;
      const timer = window.setTimeout(() => {
        timedOut = true;
        requestAbort.abort();
      }, WORKSPACE_FETCH_TIMEOUT_MS);

      if (!options?.silent) {
        setLoading(true);
        setError(null);
        setNotFound(false);
      }

      try {
        const data = await api.getCase(caseId, { signal: requestAbort.signal });
        if (caseIdRef.current !== caseId) return;
        setWorkspace(data);
        workspaceRef.current = data;
        if (!options?.silent) {
          setError(null);
          setNotFound(false);
        }
      } catch (err) {
        if (caseIdRef.current !== caseId) return;
        const aborted =
          (err instanceof DOMException && err.name === "AbortError") ||
          (err instanceof Error && err.name === "AbortError");
        if (aborted) {
          // Intentional cancel (nav/unmount) — do not paint a timeout error.
          if (!timedOut) return;
          if (!options?.silent) {
            setError(
              "Timed out loading case workspace. Retry from the case list.",
            );
            if (!workspaceRef.current) {
              setWorkspace(null);
            }
          }
          return;
        }
        const missing = isNotFound(err);
        if (missing) setNotFound(true);
        if (!options?.silent) {
          setError(
            missing
              ? "This case no longer exists. It may have been deleted or was a temporary verification run."
              : err instanceof Error
                ? err.message
                : "Failed to load case",
          );
          // Keep last-good workspace so soft-nav does not stick on
          // "Loading…" / "0 B evidence" after a hitch.
          if (missing || !workspaceRef.current) {
            setWorkspace(null);
            workspaceRef.current = null;
          }
        }
      } finally {
        window.clearTimeout(timer);
        if (abortRef.current === requestAbort) abortRef.current = null;
        if (!options?.silent && caseIdRef.current === caseId) {
          setLoading(false);
        }
      }
    },
    [caseId],
  );

  useEffect(() => {
    if (!caseId) return;
    setWorkspace(null);
    workspaceRef.current = null;
    setError(null);
    setNotFound(false);
    setLoading(true);
    void refresh();
    return () => {
      abortRef.current?.abort();
    };
  }, [caseId, refresh]);

  useEffect(() => {
    if (!caseId) return;
    const timer = window.setInterval(() => {
      void refresh({ silent: true });
    }, 30000);
    return () => window.clearInterval(timer);
  }, [caseId, refresh]);

  const value = useMemo(
    () => ({ caseId, workspace, loading, error, notFound, refresh }),
    [caseId, workspace, loading, error, notFound, refresh],
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCaseContext() {
  const ctx = useContext(CaseContext);
  if (!ctx) throw new Error("useCaseContext must be used within CaseProvider");
  return ctx;
}
