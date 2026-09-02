import { useMemo, useState } from "react";
import { Grid3X3, LayoutList, Plus, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { useCaseContext } from "@/context/CaseContext";
import {
  FacetedFilters,
  type FilterGroup,
} from "@/components/visily/FacetedFilters";
import { EvidenceInspector } from "@/components/visily/EvidenceInspector";
import { CatalogStatStrip } from "@/components/visily/CatalogStatStrip";
import { Button } from "@/components/ui/button";
import { formatBytes, shortHash } from "@/lib/utils";
import {
  failedJobCount,
  runningJobs as listRunningJobs,
  totalRecoveredSegments,
} from "@/lib/caseStats";
import type { EvidenceRecord } from "@/lib/api";
import { HardDrive, FlaskConical, Database } from "lucide-react";

const categoryIcons = {
  disk: HardDrive,
  specimen: FlaskConical,
  block: Database,
};

function inferCategory(item: EvidenceRecord): keyof typeof categoryIcons {
  const method = (item.acquisition_method || "").toLowerCase();
  if (method.includes("synthetic") || method.includes("specimen"))
    return "specimen";
  if (method.includes("physical") || item.media_type?.includes("physical"))
    return "block";
  return "disk";
}

function inferStatus(item: EvidenceRecord): string {
  const verification = (item.verification_status || "").toLowerCase();
  if (verification === "verified") return "verified";
  if (verification === "pending") return "awaiting hash";
  if (verification === "failed") return "failed";
  return item.acquisition_status === "complete" ? "verified" : "parsing";
}

function statusBadgeClass(status: string) {
  if (status === "verified") return "visily-badge-success";
  if (status === "awaiting hash") return "visily-badge-active";
  return "visily-badge-danger";
}

function categoryLabel(cat: keyof typeof categoryIcons) {
  if (cat === "specimen") return "lab specimen";
  if (cat === "block") return "block image";
  return "disk image";
}

export function CaseEvidenceCatalogPage() {
  const { caseId, workspace } = useCaseContext();
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [filters, setFilters] = useState<Record<string, Set<string>>>({
    category: new Set(),
    status: new Set(),
    type: new Set(),
  });
  const [sort, setSort] = useState<"recent" | "size" | "name">("recent");

  const evidence = workspace?.evidence ?? [];
  const custody = workspace?.custody ?? [];
  const jobs = workspace?.jobs ?? [];

  const filterGroups: FilterGroup[] = useMemo(
    () => [
      {
        id: "category",
        label: "Category",
        options: [
          {
            id: "disk",
            label: "Disk image",
            count: evidence.filter((e) => inferCategory(e) === "disk").length,
          },
          {
            id: "specimen",
            label: "Lab specimen",
            count: evidence.filter((e) => inferCategory(e) === "specimen")
              .length,
          },
          {
            id: "block",
            label: "Block imaging",
            count: evidence.filter((e) => inferCategory(e) === "block").length,
          },
        ],
      },
      {
        id: "status",
        label: "Verification status",
        options: [
          {
            id: "verified",
            label: "Verified",
            count: evidence.filter((e) => inferStatus(e) === "verified").length,
          },
          {
            id: "parsing",
            label: "Parsing",
            count: evidence.filter((e) => inferStatus(e) === "parsing").length,
          },
          {
            id: "awaiting hash",
            label: "Awaiting hash",
            count: evidence.filter((e) => inferStatus(e) === "awaiting hash")
              .length,
          },
        ],
      },
      {
        id: "type",
        label: "Evidence type",
        options: [
          {
            id: "dvr",
            label: "DVR/NVR image",
            count: evidence.filter(
              (e) =>
                e.media_type?.includes("dvr") ||
                /\.(dav|mp4|avi)$/i.test(e.filename) ||
                e.acquisition_method?.includes("logical"),
            ).length,
          },
          {
            id: "dd",
            label: "Raw DD / IMG",
            count: evidence.filter((e) =>
              /\.(dd|img|raw|bin)$/i.test(e.filename),
            ).length,
          },
          {
            id: "e01",
            label: "E01 (input)",
            count: evidence.filter((e) => /\.(e01|001)$/i.test(e.filename))
              .length,
          },
        ],
      },
    ],
    [evidence],
  );

  const filtered = useMemo(() => {
    const list = evidence.filter((item) => {
      const q = query.trim().toLowerCase();
      if (
        q &&
        !item.filename.toLowerCase().includes(q) &&
        !item.id.toLowerCase().includes(q)
      )
        return false;

      const cat = inferCategory(item);
      if (filters.category.size > 0 && !filters.category.has(cat)) return false;

      const st = inferStatus(item);
      if (filters.status.size > 0 && !filters.status.has(st)) return false;

      if (filters.type.size > 0) {
        const types = Array.from(filters.type);
        const match = types.some((t) => {
          if (t === "dd") return item.filename.match(/\.(dd|img|raw|bin)$/i);
          if (t === "e01") return item.filename.match(/\.(e01|001)$/i);
          if (t === "dvr")
            return (
              item.media_type?.includes("dvr") ||
              item.filename.includes("dvr") ||
              item.filename.includes("specimen")
            );
          return false;
        });
        if (!match) return false;
      }

      return true;
    });

    return [...list].sort((a, b) => {
      if (sort === "size") return b.size_bytes - a.size_bytes;
      if (sort === "name") return a.filename.localeCompare(b.filename);
      return (
        new Date(b.acquired_at).getTime() - new Date(a.acquired_at).getTime()
      );
    });
  }, [evidence, query, filters, sort]);

  const selected =
    filtered.find((e) => e.id === selectedId) ?? filtered[0] ?? null;

  function toggleFilter(groupId: string, optionId: string) {
    setFilters((prev) => {
      const next = { ...prev, [groupId]: new Set(prev[groupId]) };
      if (next[groupId].has(optionId)) next[groupId].delete(optionId);
      else next[groupId].add(optionId);
      return next;
    });
  }

  const totalBytes = evidence.reduce((s, e) => s + e.size_bytes, 0);
  const activeJobs = listRunningJobs(jobs).length;
  const segmentTotal = totalRecoveredSegments(jobs);
  const auditErrors = failedJobCount(jobs);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="visily-catalog-toolbar">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            className="field h-9 w-full pl-9 uppercase tracking-wide"
            placeholder="Search evidence catalog…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <p className="mono text-[10px] uppercase text-[var(--text-tertiary)]">
          Total: {evidence.length} | Filtered: {filtered.length}
        </p>
        <div
          className="flex rounded-md border"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <button
            type="button"
            className={`flex h-8 w-8 items-center justify-center ${view === "grid" ? "bg-[var(--accent-soft)] text-[var(--accent-500)]" : "text-[var(--text-tertiary)]"}`}
            onClick={() => setView("grid")}
          >
            <Grid3X3 className="h-4 w-4" />
          </button>
          <button
            type="button"
            className={`flex h-8 w-8 items-center justify-center border-l ${view === "list" ? "bg-[var(--accent-soft)] text-[var(--accent-500)]" : "text-[var(--text-tertiary)]"}`}
            style={{ borderColor: "var(--border-subtle)" }}
            onClick={() => setView("list")}
          >
            <LayoutList className="h-4 w-4" />
          </button>
        </div>
        <select
          className="field h-9 w-auto text-[11px] uppercase"
          value={sort}
          onChange={(e) =>
            setSort(e.target.value as "recent" | "size" | "name")
          }
        >
          <option value="recent">Sort: Recent</option>
          <option value="size">Sort: Size</option>
          <option value="name">Sort: Name</option>
        </select>
        <Button asChild size="sm">
          <Link to={`/cases/${caseId}/acquire`}>
            <Plus className="h-4 w-4" />
            Add evidence
          </Link>
        </Button>
      </div>

      <p className="visily-breadcrumb-trail px-1">
        <span>Forensic_root</span>
        <span>›</span>
        <span>Cases</span>
        <span>›</span>
        <span>{caseId?.slice(0, 8)}</span>
        <span>›</span>
        <span className="text-[var(--accent-500)]">
          Catalog · {filtered.length} item{filtered.length === 1 ? "" : "s"}
        </span>
      </p>

      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden">
        <FacetedFilters
          groups={filterGroups}
          selected={filters}
          onToggle={toggleFilter}
          onReset={() => {
            setFilters({
              category: new Set(),
              status: new Set(),
              type: new Set(),
            });
          }}
        />

        <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="visily-card flex flex-1 items-center justify-center p-12">
              <div className="text-center">
                <p className="text-[14px] font-medium text-[var(--text-primary)]">
                  No evidence in catalog
                </p>
                <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
                  Acquire media or import a signed bundle to populate the
                  catalog.
                </p>
                <Button asChild className="mt-4" size="sm">
                  <Link to={`/cases/${caseId}/acquire`}>Start acquisition</Link>
                </Button>
              </div>
            </div>
          ) : view === "grid" ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((item) => {
                const cat = inferCategory(item);
                const Icon = categoryIcons[cat];
                const active = selected?.id === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`visily-evidence-grid-card text-left ${active ? "visily-evidence-grid-card-selected" : ""}`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
                        {cat}
                      </span>
                      <span
                        className={`visily-badge text-[8px] ${statusBadgeClass(inferStatus(item))}`}
                      >
                        {inferStatus(item)}
                      </span>
                    </div>
                    <div className="visily-evidence-thumb mb-3 h-28">
                      <Icon
                        className="h-10 w-10 text-[var(--accent-500)]"
                        strokeWidth={1.25}
                      />
                    </div>
                    <p className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
                      {item.filename}
                    </p>
                    <p className="mono mt-1 text-[10px] text-[var(--text-tertiary)]">
                      {item.id.slice(0, 12)}
                    </p>
                    <p className="mono mt-2 text-[11px] text-[var(--text-secondary)]">
                      {formatBytes(item.size_bytes)} ·{" "}
                      {categoryLabel(inferCategory(item))}
                    </p>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="visily-card overflow-hidden">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr
                      key={item.id}
                      className={
                        selected?.id === item.id
                          ? "row-selected cursor-pointer"
                          : "cursor-pointer"
                      }
                      onClick={() => setSelectedId(item.id)}
                    >
                      <td className="font-medium">{item.filename}</td>
                      <td className="mono">{formatBytes(item.size_bytes)}</td>
                      <td>
                        <span
                          className={`visily-badge text-[9px] ${statusBadgeClass(inferStatus(item))}`}
                        >
                          {inferStatus(item)}
                        </span>
                      </td>
                      <td className="mono text-[11px]">
                        {shortHash(item.sha256)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <CatalogStatStrip
            storageBytes={totalBytes}
            artefactCount={segmentTotal}
            processingJobs={activeJobs}
            auditErrors={auditErrors}
          />
        </div>

        <EvidenceInspector item={selected} custodyEvents={custody} />
      </div>
    </div>
  );
}
