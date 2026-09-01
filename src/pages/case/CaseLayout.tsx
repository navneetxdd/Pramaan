import { useEffect } from "react";
import { Outlet, useNavigate, useParams, Link } from "react-router-dom";
import { CaseProvider, useCaseContext } from "@/context/CaseContext";
import { Button } from "@/components/ui/button";
import { removeRecentCase } from "@/lib/recentCases";
import { toastErrorOnce } from "@/lib/toast";

function CaseLayoutInner() {
  const { caseId, workspace, loading, error, notFound } = useCaseContext();
  const navigate = useNavigate();

  useEffect(() => {
    if (!notFound || !caseId) return;
    removeRecentCase(caseId);
    toastErrorOnce("case-not-found", "Case not found — returning to registry");
    navigate("/cases", { replace: true });
  }, [notFound, caseId, navigate]);

  if (loading && !workspace) {
    return <p className="text-[13px] text-[var(--text-tertiary)]">Loading case workspace…</p>;
  }
  if (error && !notFound) {
    return (
      <div className="visily-card p-8 text-center">
        <p className="text-[14px] text-[var(--status-danger)]">{error}</p>
        <Button asChild className="mt-4" variant="secondary">
          <Link to="/cases">Back to cases</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Outlet />
    </div>
  );
}

export function CaseLayout() {
  const { caseId } = useParams();
  if (!caseId) return null;
  return (
    <CaseProvider>
      <CaseLayoutInner />
    </CaseProvider>
  );
}
