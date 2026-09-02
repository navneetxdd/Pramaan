import { NavLink, useLocation, useParams } from "react-router-dom";

import {
  Briefcase,
  FileText,
  LayoutDashboard,
  FolderKanban,
  HardDriveDownload,
  LayoutGrid,
  Lock,
  ScanEye,
  ScanSearch,
  Settings,
  ShieldCheck,
  Fingerprint,
  GanttChartSquare,
  Radio,
} from "lucide-react";

import { useEffect, useState } from "react";

import { PramaanLogo } from "@/components/brand/PramaanLogo";

import { api } from "@/lib/api";

import { totalRecoveredSegments } from "@/lib/caseStats";

import { cn } from "@/lib/utils";

type NavItem = {
  to: string;

  label: string;

  icon: typeof FolderKanban;

  end?: boolean;

  step?: number;

  requiresEvidence?: boolean;

  requiresRecovery?: boolean;
};

const globalNav: NavItem[] = [
  { to: "/cases", label: "Cases", icon: FolderKanban, end: true },

  { to: "/settings", label: "Settings", icon: Settings },
];

const caseWorkflow: NavItem[] = [
  { to: "", label: "Overview", icon: LayoutDashboard, end: true },

  { to: "live", label: "Live devices", icon: Radio },

  { to: "acquire", label: "Acquisition", icon: HardDriveDownload, step: 1 },

  {
    to: "device-id",
    label: "Identification",
    icon: Fingerprint,
    step: 2,
    requiresEvidence: true,
  },

  {
    to: "recover",
    label: "Recovery",
    icon: ScanSearch,
    step: 3,
    requiresEvidence: true,
  },

  {
    to: "timeline",
    label: "Timeline & playback",
    icon: GanttChartSquare,
    step: 4,
    requiresRecovery: true,
  },

  {
    to: "ai-analytics",
    label: "Findings",
    icon: ScanEye,
    step: 5,
    requiresRecovery: true,
  },

  { to: "custody", label: "Custody", icon: ShieldCheck },

  { to: "report", label: "Report", icon: FileText },

  { to: "evidence", label: "Evidence catalog", icon: LayoutGrid },

  { to: "jobs", label: "Job log", icon: Briefcase },
];

export function ModuleSidebar() {
  const { caseId } = useParams();

  const location = useLocation();

  const inCase =
    Boolean(caseId) && location.pathname.startsWith(`/cases/${caseId}`);

  const [evidenceCount, setEvidenceCount] = useState(0);

  const [segmentCount, setSegmentCount] = useState(0);

  useEffect(() => {
    if (!inCase || !caseId) {
      setEvidenceCount(0);

      setSegmentCount(0);

      return;
    }

    let cancelled = false;

    async function loadCounts() {
      try {
        const workspace = await api.getCase(caseId!);

        if (!cancelled) {
          setEvidenceCount(workspace.evidence.length);

          setSegmentCount(totalRecoveredSegments(workspace.jobs));
        }
      } catch {
        if (!cancelled) {
          setEvidenceCount(0);

          setSegmentCount(0);
        }
      }
    }

    void loadCounts();

    const timer = window.setInterval(() => void loadCounts(), 5000);

    return () => {
      cancelled = true;

      window.clearInterval(timer);
    };
  }, [caseId, inCase]);

  function caseDest(item: NavItem): string {
    if (!caseId) return "/cases";

    if (item.to === "") return `/cases/${caseId}`;

    return `/cases/${caseId}/${item.to}`;
  }

  function isLocked(item: NavItem): boolean {
    if (item.requiresRecovery) return segmentCount <= 0;

    if (item.requiresEvidence) return evidenceCount <= 0;

    return false;
  }

  function renderCaseItem(item: NavItem) {
    const dest = caseDest(item);

    const locked = isLocked(item);

    if (locked) {
      return (
        <span
          key={item.label}

          className="visily-nav-item cursor-not-allowed opacity-45"

          title={
            item.requiresRecovery
              ? "Run recovery first"
              : "Acquire evidence first"
          }
        >
          <Lock className="h-4 w-4" strokeWidth={1.75} />

          {item.step ? `${item.step}. ` : ""}

          {item.label}
        </span>
      );
    }

    return (
      <NavLink key={item.label} to={dest} end={item.end}>
        {({ isActive }) => (
          <span
            className={cn(
              "visily-nav-item",
              isActive && "visily-nav-item-active",
            )}
          >
            <item.icon className="h-4 w-4" strokeWidth={1.75} />

            {item.step ? `${item.step}. ` : ""}

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
      <div
        className="border-b px-4 py-4"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <PramaanLogo />
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {!inCase ? (
          <>
            {globalNav.map((item) => (
              <NavLink key={item.label} to={item.to} end={item.end}>
                {({ isActive }) => (
                  <span
                    className={cn(
                      "visily-nav-item",
                      isActive && "visily-nav-item-active",
                    )}
                  >
                    <item.icon className="h-4 w-4" strokeWidth={1.75} />

                    {item.label}
                  </span>
                )}
              </NavLink>
            ))}

            <p className="mx-2 mt-4 rounded-md bg-[var(--surface-3)] px-2 py-2 text-[10px] leading-relaxed text-[var(--text-tertiary)]">
              Open or create a case to unlock the workflow.
            </p>
          </>
        ) : (
          <>
            <p className="px-2 py-1 text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
              Investigation workflow
            </p>

            {caseWorkflow.map(renderCaseItem)}
          </>
        )}
      </nav>

      {inCase ? (
        <div
          className="border-t p-3"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <NavLink to="/cases">
            <span className="visily-nav-item text-[11px] normal-case tracking-normal">
              ← All cases
            </span>
          </NavLink>

          <p className="mono mt-2 truncate text-[10px] text-[var(--text-tertiary)]">
            {caseId}
          </p>
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

      live: "Live devices",

      evidence: "Evidence catalog",

      acquire: "Acquisition",

      jobs: "Job log",

      "device-id": "Device identification",

      recover: "Recovery",

      timeline: "Timeline & playback",

      custody: "Chain of custody",

      report: "Case report",

      "ai-analytics": "Investigative findings",
    };

    return { section: "Case workspace", page: labels[step] ?? "Overview" };
  }

  if (pathname.startsWith("/settings"))
    return { section: "Pramaan", page: "Settings" };

  return { section: "Pramaan", page: "Case registry" };
}
