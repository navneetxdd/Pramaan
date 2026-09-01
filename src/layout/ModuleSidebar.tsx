import { NavLink, useLocation, useParams } from "react-router-dom";
import {
  BadgeCheck,
  Briefcase,
  FileText,
  LayoutDashboard,
  FolderKanban,
  HardDriveDownload,
  LayoutGrid,
  ScanEye,
  ScanSearch,
  Settings,
  ShieldCheck,
  Fingerprint,
  GanttChartSquare,
} from "lucide-react";
import { toast } from "sonner";
import { PramaanShield } from "@/components/brand/PramaanShield";
import { mostRecentCaseId } from "@/lib/recentCases";
import { cn } from "@/lib/utils";

type NavItem = {
  to: string;
  label: string;
  icon: typeof FolderKanban;
  end?: boolean;
  requiresCase?: boolean;
  globalOnly?: boolean;
};

/** Case workflow nav order — evidence-first forensic workstation. */
const navItems: NavItem[] = [
  { to: "/cases", label: "Cases", icon: FolderKanban, end: true },
  { to: "", label: "Overview", icon: LayoutDashboard, requiresCase: true, end: true },
  { to: "acquire", label: "Acquisition", icon: HardDriveDownload, requiresCase: true },
  { to: "device-id", label: "Identification", icon: Fingerprint, requiresCase: true },
  { to: "recover", label: "Recovery", icon: ScanSearch, requiresCase: true },
  { to: "timeline", label: "Timeline", icon: GanttChartSquare, requiresCase: true },
  { to: "ai-analytics", label: "Findings", icon: ScanEye, requiresCase: true },
  { to: "custody", label: "Custody", icon: ShieldCheck, requiresCase: true },
  { to: "report", label: "Report", icon: FileText, requiresCase: true },
  { to: "evidence", label: "Evidence", icon: LayoutGrid, requiresCase: true },
  { to: "jobs", label: "Jobs", icon: Briefcase, requiresCase: true },
  { to: "/tool-verification", label: "Validation", icon: BadgeCheck, globalOnly: true },
  { to: "/settings", label: "Settings", icon: Settings, globalOnly: true },
];

export function ModuleSidebar() {
  const { caseId } = useParams();
  const location = useLocation();
  const inCase = Boolean(caseId) && location.pathname.startsWith(`/cases/${caseId}`);
  const fallbackCaseId = mostRecentCaseId();

  function resolveTo(item: NavItem): string {
    if (item.globalOnly || item.to.startsWith("/")) return item.to;
    const targetCase = inCase ? caseId : fallbackCaseId;
    if (!targetCase) return "/cases";
    if (item.to === "") return `/cases/${targetCase}`;
    return `/cases/${targetCase}/${item.to}`;
  }

  function onCaseNavClick(item: NavItem) {
    if (!item.requiresCase || inCase || fallbackCaseId) return;
    toast.message("Create or open a case from the Cases screen first.");
  }

  function renderItem(item: NavItem) {
    const dest = resolveTo(item);
    const needsCasePrompt = item.requiresCase && !inCase && !fallbackCaseId;

    return (
      <NavLink key={item.label} to={dest} end={item.end} onClick={() => onCaseNavClick(item)}>
        {({ isActive }) => (
          <span
            className={cn(
              "visily-nav-item",
              isActive && !needsCasePrompt && "visily-nav-item-active",
              needsCasePrompt && "opacity-70",
            )}
            title={needsCasePrompt ? "Open a case first" : undefined}
          >
            <item.icon className="h-4 w-4" strokeWidth={1.75} />
            {item.label}
          </span>
        )}
      </NavLink>
    );
  }

  return (
    <aside
      className="flex shrink-0 flex-col border-r"
      style={{
        width: "var(--sidebar-width)",
        borderColor: "var(--border-subtle)",
        background: "var(--surface-0)",
      }}
    >
      <div className="flex items-center gap-3 border-b px-4 py-4" style={{ borderColor: "var(--border-subtle)" }}>
        <PramaanShield />
        <p className="text-[13px] font-bold tracking-[0.14em] text-[var(--text-primary)]">PRAMAN</p>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">{navItems.map(renderItem)}</nav>

      {inCase ? (
        <div className="border-t p-3" style={{ borderColor: "var(--border-subtle)" }}>
          <NavLink to="/cases">
            <span className="visily-nav-item text-[10px] normal-case tracking-normal">← All cases</span>
          </NavLink>
          <p className="mono mt-2 truncate text-[10px] text-[var(--text-tertiary)]">{caseId}</p>
        </div>
      ) : fallbackCaseId ? (
        <div className="border-t p-3" style={{ borderColor: "var(--border-subtle)" }}>
          <p className="text-[10px] text-[var(--text-tertiary)]">Case tabs route to your last open case.</p>
        </div>
      ) : null}
    </aside>
  );
}

export function useBreadcrumb(): { section: string; page: string } {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);

  if (pathname.startsWith("/cases/") && parts.length >= 2) {
    const step = parts[2] ?? "dashboard";
    const labels: Record<string, string> = {
      dashboard: "Case overview",
      evidence: "Evidence catalog",
      acquire: "Acquisition & preservation",
      jobs: "Parsing jobs",
      "device-id": "Device identification",
      recover: "Recovery",
      timeline: "Timeline",
      custody: "Chain of custody",
      report: "Case report",
      "ai-analytics": "Investigative findings",
    };
    return { section: "Case workspace", page: labels[step] ?? "Case dashboard" };
  }
  if (pathname.startsWith("/tool-verification")) return { section: "PRAMAN", page: "Validation" };
  if (pathname.startsWith("/settings")) return { section: "PRAMAN", page: "Settings" };
  return { section: "PRAMAN", page: "Cases" };
}
