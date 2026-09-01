import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
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

  const refresh = useCallback(async (options?: { silent?: boolean }) => {
    if (!caseId) return;
    if (!options?.silent) {
      setLoading(true);
      setError(null);
      setNotFound(false);
    }
    try {
      const data = await api.getCase(caseId);
      setWorkspace(data);
      if (!options?.silent) {
        setError(null);
        setNotFound(false);
      }
    } catch (err) {
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
        setWorkspace(null);
      }
    } finally {
      if (!options?.silent) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (!caseId) return;
    setWorkspace(null);
    setError(null);
    setNotFound(false);
    void refresh();
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
