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
  refresh: (options?: { silent?: boolean }) => Promise<void>;
};

const CaseContext = createContext<CaseContextValue | null>(null);

export function CaseProvider({ children }: { children: ReactNode }) {
  const { caseId = "" } = useParams();
  const [workspace, setWorkspace] = useState<CaseWorkspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (options?: { silent?: boolean }) => {
    if (!caseId) return;
    if (!options?.silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const data = await api.getCase(caseId);
      setWorkspace(data);
      if (!options?.silent) setError(null);
    } catch (err) {
      if (!options?.silent) {
        setError(err instanceof Error ? err.message : "Failed to load case");
        setWorkspace(null);
      }
    } finally {
      if (!options?.silent) setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!caseId) return;
    const timer = window.setInterval(() => {
      void refresh({ silent: true });
    }, 30000);
    return () => window.clearInterval(timer);
  }, [caseId, refresh]);

  const value = useMemo(
    () => ({ caseId, workspace, loading, error, refresh }),
    [caseId, workspace, loading, error, refresh],
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
}

export function useCaseContext() {
  const ctx = useContext(CaseContext);
  if (!ctx) throw new Error("useCaseContext must be used within CaseProvider");
  return ctx;
}
