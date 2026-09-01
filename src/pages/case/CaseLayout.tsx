import { Outlet, useParams, Link } from "react-router-dom";
import { CaseProvider, useCaseContext } from "@/context/CaseContext";
import { Button } from "@/components/ui/button";

function CaseLayoutInner() {
  const { caseId, workspace, loading, error } = useCaseContext();

  if (loading && !workspace) {
    return <p className="text-[13px] text-[var(--text-tertiary)]">Loading case workspace…</p>;
  }
  if (error) {
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
