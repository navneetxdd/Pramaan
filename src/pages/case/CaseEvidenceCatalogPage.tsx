import { useCallback, useMemo, useState } from "react";
import {
  Database,
  FileVideo,
  Grid3X3,
  HardDrive,
  HelpCircle,
  LayoutList,
  Plus,
  Search,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useCaseContext } from "@/context/CaseContext";
import {
  FacetedFilters,
  type FilterGroup,
} from "@/components/visily/FacetedFilters";
import { EvidenceInspector } from "@/components/visily/EvidenceInspector";
import { EvidenceComparisonBar } from "@/components/visily/EvidenceComparisonBar";
import { CatalogStatStrip } from "@/components/visily/CatalogStatStrip";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, shortHash } from "@/lib/utils";
import {
  failedJobCount,
  runningJobs as listRunningJobs,
  totalRecoveredSegments,
} from "@/lib/caseStats";
import type { EvidenceRecord } from "@/lib/api";
import {
  categoryDescription,
  categoryLabel,
  categoryOf,
  crossCheckHash,
  EVIDENCE_CATEGORIES,
  hashCrossCheckLabel,
  isKnownMediaType,
  isKnownVerificationStatus,
  KNOWN_VERIFICATION_STATUSES,
  MEDIA_TYPES,
  mediaTypeLabel,
  verificationStatusLabel,
  verificationStatusOf,
  verificationStatusTone,
  type EvidenceCategory,
  type HashCrossCheck,
} from "@/lib/evidenceCatalog";

const CATEGORY_ICONS: Record<EvidenceCategory, typeof HardDrive> = {
  block: Database,
  disk: HardDrive,
  logical: FileVideo,
  unclassified: HelpCircle,
};

type SortKey = "recent" | "size" | "name";
type ViewMode = "grid" | "list";
type FilterState = {
  category: Set<string>;
  status: Set<string>;
  media: Set<string>;
};

/** Always construct fresh Sets — a shared constant would let one page's
 *  reset alias another's filter state. */
function emptyFilters(): FilterState {
  return { category: new Set(), status: new Set(), media: new Set() };
}

export function CaseEvidenceCatalogPage() {
  const { caseId, workspace, loading } = useCaseContext();
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("grid");
  const [filters, setFilters] = useState<FilterState>(emptyFilters);
  const [sort, setSort] = useState<SortKey>("recent");
  const [comparing, setComparing] = useState<Set<string>>(new Set());

  const evidence = workspace?.evidence ?? [];
  const custody = workspace?.custody ?? [];
  const jobs = workspace?.jobs ?? [];

  // The workspace endpoint returns the case's full evidence list in one
  // response — there is no pagination or server-side sort to defer to — so
  // every predicate below runs over `evidence` in full, never over a rendered
  // slice. If that endpoint ever paginates, these must move server-side.
  const matchers = useMemo(
    () => buildMatchers(query, filters),
    [query, filters],
  );

  const filtered = useMemo(() => {
    const list = evidence.filter(
      (item) =>
        matchers.text(item) &&
        matchers.category(item) &&
        matchers.status(item) &&
        matchers.media(item),
    );
    return sortEvidence(list, sort);
  }, [evidence, matchers, sort]);

  /**
   * Facet counts are computed against the full dataset under every *other*
   * active filter, so a count states exactly how many items clicking that
   * option would leave — not a fixed total that stops agreeing with the table
   * the moment a second facet is applied.
   */
  const filterGroups: FilterGroup[] = useMemo(() => {
    const countUnder = (
      exclude: keyof FilterState,
      predicate: (item: EvidenceRecord) => boolean,
    ) =>
      evidence.filter((item) => {
        if (!matchers.text(item)) return false;
        if (exclude !== "category" && !matchers.category(item)) return false;
        if (exclude !== "status" && !matchers.status(item)) return false;
        if (exclude !== "media" && !matchers.media(item)) return false;
        return predicate(item);
      }).length;

    // Status options are the engine's own verification_status vocabulary, plus
    // any value actually present on this case that this build does not know —
    // an unknown value is surfaced as a facet rather than silently dropped.
    const presentStatuses = new Set(evidence.map(verificationStatusOf));
    const unknownStatuses = [...presentStatuses]
      .filter((value) => !isKnownVerificationStatus(value))
      .sort();
    const presentMediaTypes = new Set(evidence.map((item) => item.media_type));
    const unknownMediaTypes = [...presentMediaTypes]
      .filter((value) => !isKnownMediaType(value))
      .sort();

    return [
      {
        id: "category",
        label: "Category",
        options: EVIDENCE_CATEGORIES.map((category) => ({
          id: category,
          label: categoryLabel(category),
          hint: categoryDescription(category),
          count: countUnder(
            "category",
            (item) => categoryOf(item) === category,
          ),
        })),
      },
      {
        id: "status",
        label: "Verification status",
        options: [
          ...KNOWN_VERIFICATION_STATUSES.map((status) => ({
            id: status,
            label: verificationStatusLabel(status),
            hint: `devices.verification_status = "${status}"`,
            count: countUnder(
              "status",
              (item) => verificationStatusOf(item) === status,
            ),
          })),
          ...unknownStatuses.map((status) => ({
            id: status,
            label: `${status} (unrecognised)`,
            hint: "The engine emitted a verification_status this build does not recognise. Report it.",
            count: countUnder(
              "status",
              (item) => verificationStatusOf(item) === status,
            ),
          })),
        ],
      },
      {
        id: "media",
        label: "Media type",
        options: [
          ...MEDIA_TYPES.map((mediaType) => ({
            id: mediaType,
            label: mediaTypeLabel(mediaType),
            hint: `devices media_type = "${mediaType}"`,
            count: countUnder("media", (item) => item.media_type === mediaType),
          })),
          ...unknownMediaTypes.map((mediaType) => ({
            id: mediaType,
            label: `${mediaType || "(none)"} (unrecognised)`,
            hint: "The engine emitted a media_type this build does not recognise. Report it.",
            count: countUnder("media", (item) => item.media_type === mediaType),
          })),
        ],
      },
    ];
  }, [evidence, matchers]);

  // Custody rows are bound to an item by the hash the log stored for it, so the
  // cross-check is precomputed once per filtered set rather than per row render.
  const crossChecks = useMemo(() => {
    const map = new Map<string, HashCrossCheck>();
    for (const item of filtered) {
      map.set(item.id, crossCheckHash(item, custody, evidence));
    }
    return map;
  }, [filtered, custody, evidence]);

  const selected = filtered.find((item) => item.id === selectedId) ?? null;

  const comparisonItems = useMemo(
    () => filtered.filter((item) => comparing.has(item.id)),
    [filtered, comparing],
  );

  const toggleFilter = useCallback((groupId: string, optionId: string) => {
    setFilters((previous) => {
      const key = groupId as keyof FilterState;
      const next = new Set(previous[key]);
      if (next.has(optionId)) next.delete(optionId);
      else next.add(optionId);
      return { ...previous, [key]: next };
    });
  }, []);

  const toggleComparison = useCallback((id: string) => {
    setComparing((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const totalBytes = evidence.reduce((sum, item) => sum + item.size_bytes, 0);
  const filtersActive =
    query.trim().length > 0 ||
    filters.category.size > 0 ||
    filters.status.size > 0 ||
    filters.media.size > 0;
  const showSkeleton = loading && evidence.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="visily-catalog-toolbar">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            className="field h-9 w-full pl-9 uppercase tracking-wide"
            placeholder="Search filename, id or SHA-256…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search evidence catalog"
          />
        </div>
        <p className="mono text-[10px] uppercase text-[var(--text-tertiary)]">
          {showSkeleton
            ? "Loading…"
            : `Total: ${evidence.length} | Filtered: ${filtered.length}`}
        </p>
        <div
          className="flex rounded-md border"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <button
            type="button"
            aria-pressed={view === "grid"}
            aria-label="Grid view"
            className={`flex h-8 w-8 items-center justify-center ${view === "grid" ? "bg-[var(--accent-soft)] text-[var(--accent-500)]" : "text-[var(--text-tertiary)]"}`}
            onClick={() => setView("grid")}
          >
            <Grid3X3 className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-pressed={view === "list"}
            aria-label="List view"
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
          onChange={(event) => setSort(event.target.value as SortKey)}
          aria-label="Sort evidence"
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

      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden">
        <FacetedFilters
          groups={filterGroups}
          selected={filters}
          onToggle={toggleFilter}
          onReset={() => setFilters(emptyFilters())}
          loading={showSkeleton}
        />

        <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
          {showSkeleton ? (
            view === "grid" ? (
              <GridSkeleton />
            ) : (
              <ListSkeleton />
            )
          ) : filtered.length === 0 ? (
            <EmptyState
              caseId={caseId}
              reason={
                evidence.length === 0 ? "no-evidence" : ("no-matches" as const)
              }
              onClearFilters={() => {
                setQuery("");
                setFilters(emptyFilters());
              }}
            />
          ) : view === "grid" ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((item) => (
                <EvidenceCard
                  key={item.id}
                  item={item}
                  crossCheck={crossChecks.get(item.id)}
                  active={selected?.id === item.id}
                  onSelect={() => setSelectedId(item.id)}
                />
              ))}
            </div>
          ) : (
            <EvidenceTable
              items={filtered}
              crossChecks={crossChecks}
              selectedId={selected?.id ?? null}
              comparing={comparing}
              onSelect={setSelectedId}
              onToggleComparison={toggleComparison}
              onToggleAllComparison={(checked) =>
                setComparing(
                  checked
                    ? new Set(filtered.map((item) => item.id))
                    : new Set(),
                )
              }
            />
          )}

          {view === "list" ? (
            <EvidenceComparisonBar
              items={comparisonItems}
              onRemove={toggleComparison}
              onClear={() => setComparing(new Set())}
            />
          ) : null}

          <CatalogStatStrip
            storageBytes={totalBytes}
            artefactCount={totalRecoveredSegments(jobs)}
            processingJobs={listRunningJobs(jobs).length}
            auditErrors={failedJobCount(jobs)}
          />
        </div>

        <EvidenceInspector
          item={selected}
          custodyEvents={custody}
          caseEvidence={evidence}
          caseId={caseId}
          loading={showSkeleton}
        />
      </div>

      {!showSkeleton && filtersActive && filtered.length > 0 ? (
        <p className="sr-only" role="status">
          {filtered.length} of {evidence.length} evidence items match the
          current filter.
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Filtering and sorting                                               */
/* ------------------------------------------------------------------ */

function buildMatchers(query: string, filters: FilterState) {
  const needle = query.trim().toLowerCase();
  return {
    text(item: EvidenceRecord) {
      if (!needle) return true;
      return (
        item.filename.toLowerCase().includes(needle) ||
        item.id.toLowerCase().includes(needle) ||
        (item.sha256 ?? "").toLowerCase().includes(needle)
      );
    },
    category(item: EvidenceRecord) {
      if (filters.category.size === 0) return true;
      return filters.category.has(categoryOf(item));
    },
    status(item: EvidenceRecord) {
      if (filters.status.size === 0) return true;
      return filters.status.has(verificationStatusOf(item));
    },
    media(item: EvidenceRecord) {
      if (filters.media.size === 0) return true;
      return filters.media.has(item.media_type);
    },
  };
}

function sortEvidence(list: EvidenceRecord[], sort: SortKey): EvidenceRecord[] {
  const sorted = [...list];
  if (sort === "size") {
    sorted.sort((a, b) => b.size_bytes - a.size_bytes);
  } else if (sort === "name") {
    sorted.sort((a, b) =>
      a.filename.localeCompare(b.filename, undefined, { numeric: true }),
    );
  } else {
    // An unparseable or absent acquired_at sorts last rather than to the epoch,
    // which would otherwise present an undated item as the oldest acquisition.
    sorted.sort((a, b) => acquiredTime(b) - acquiredTime(a));
  }
  return sorted;
}

function acquiredTime(item: EvidenceRecord): number {
  const value = Date.parse(item.acquired_at ?? "");
  return Number.isNaN(value) ? Number.NEGATIVE_INFINITY : value;
}

/* ------------------------------------------------------------------ */
/* Integrity presentation                                              */
/* ------------------------------------------------------------------ */

function crossCheckTone(check?: HashCrossCheck) {
  switch (check?.state) {
    case "match":
      return { icon: ShieldCheck, color: "var(--status-success)" };
    case "mismatch":
      return { icon: ShieldAlert, color: "var(--status-danger)" };
    case "no_stored_hash":
      return { icon: ShieldQuestion, color: "var(--status-warning)" };
    default:
      return { icon: ShieldQuestion, color: "var(--text-tertiary)" };
  }
}

function IntegrityMark({ check }: { check?: HashCrossCheck }) {
  const { icon: Icon, color } = crossCheckTone(check);
  const label = check
    ? hashCrossCheckLabel(check)
    : "Hash cross-check unavailable";
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{ color }}
      title={label}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  );
}

function StatusBadge({ item }: { item: EvidenceRecord }) {
  const status = verificationStatusOf(item);
  const tone = verificationStatusTone(status);
  const className =
    tone === "success"
      ? "visily-badge-success"
      : tone === "danger"
        ? "visily-badge-danger"
        : tone === "warning"
          ? "visily-badge-active"
          : "visily-badge-neutral";
  return (
    <span
      className={`visily-badge text-[9px] ${className}`}
      style={
        tone === "warning"
          ? {
              background: "rgba(217, 119, 6, 0.15)",
              color: "var(--status-warning)",
            }
          : undefined
      }
      title={`devices.verification_status = "${status}"`}
    >
      {verificationStatusLabel(status)}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Grid view                                                           */
/* ------------------------------------------------------------------ */

function EvidenceCard({
  item,
  crossCheck,
  active,
  onSelect,
}: {
  item: EvidenceRecord;
  crossCheck?: HashCrossCheck;
  active: boolean;
  onSelect: () => void;
}) {
  const category = categoryOf(item);
  const Icon = CATEGORY_ICONS[category];
  const mismatch = crossCheck?.state === "mismatch";

  return (
    <button
      type="button"
      aria-pressed={active}
      className={`visily-evidence-grid-card text-left ${active ? "visily-evidence-grid-card-selected" : ""}`}
      style={
        mismatch
          ? { borderColor: "var(--status-danger)", borderWidth: 2 }
          : undefined
      }
      onClick={onSelect}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span
          className="truncate text-[9px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]"
          title={categoryDescription(category)}
        >
          {categoryLabel(category)}
        </span>
        <StatusBadge item={item} />
      </div>

      <div className="visily-evidence-thumb mb-3 flex h-28 items-center justify-center">
        <Icon
          className="h-10 w-10 text-[var(--accent-500)]"
          strokeWidth={1.25}
          aria-hidden
        />
      </div>

      <p className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
        {item.filename}
      </p>
      <p className="mono mt-1 truncate text-[10px] text-[var(--text-tertiary)]">
        {item.id.slice(0, 12)}
      </p>
      <p className="mono mt-2 text-[11px] text-[var(--text-secondary)]">
        {formatBytes(item.size_bytes)} · {mediaTypeLabel(item.media_type)}
      </p>

      {/* Integrity is stated on the card, not only in the inspector: an
          examiner scanning the grid must be able to see a disagreement between
          the record hash and the custody log without opening each item. */}
      <p
        className="mt-2 flex items-center gap-1.5 text-[10px] font-medium"
        style={{ color: crossCheckTone(crossCheck).color }}
      >
        <IntegrityMark check={crossCheck} />
        <span aria-hidden>
          {crossCheck
            ? hashCrossCheckLabel(crossCheck)
            : "Hash cross-check unavailable"}
        </span>
      </p>
    </button>
  );
}

function GridSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="visily-evidence-grid-card cursor-default">
          <div className="mb-2 flex items-center justify-between">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="mb-3 h-28 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="mt-2 h-3 w-1/3" />
          <Skeleton className="mt-2 h-3 w-1/2" />
        </div>
      ))}
      <span className="sr-only">Loading evidence catalog…</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* List view                                                           */
/* ------------------------------------------------------------------ */

function EvidenceTable({
  items,
  crossChecks,
  selectedId,
  comparing,
  onSelect,
  onToggleComparison,
  onToggleAllComparison,
}: {
  items: EvidenceRecord[];
  crossChecks: Map<string, HashCrossCheck>;
  selectedId: string | null;
  comparing: Set<string>;
  onSelect: (id: string) => void;
  onToggleComparison: (id: string) => void;
  onToggleAllComparison: (checked: boolean) => void;
}) {
  const allSelected =
    items.length > 0 && items.every((i) => comparing.has(i.id));
  const someSelected = items.some((item) => comparing.has(item.id));

  return (
    <div className="visily-card overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th className="w-9">
              <Checkbox
                checked={allSelected}
                indeterminate={someSelected && !allSelected}
                onCheckedChange={onToggleAllComparison}
                aria-label="Select all rows for comparison"
              />
            </th>
            <th>Name</th>
            <th>Category</th>
            <th>Size</th>
            <th>Verification</th>
            <th>Integrity</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const check = crossChecks.get(item.id);
            const mismatch = check?.state === "mismatch";
            return (
              <tr
                key={item.id}
                className={selectedId === item.id ? "row-selected" : undefined}
                style={
                  mismatch
                    ? {
                        background: "rgba(239, 68, 68, 0.06)",
                        boxShadow: "inset 3px 0 0 0 var(--status-danger)",
                      }
                    : undefined
                }
              >
                <td onClick={(event) => event.stopPropagation()}>
                  <Checkbox
                    checked={comparing.has(item.id)}
                    onCheckedChange={() => onToggleComparison(item.id)}
                    aria-label={`Compare ${item.filename}`}
                  />
                </td>
                <td
                  className="cursor-pointer font-medium"
                  onClick={() => onSelect(item.id)}
                >
                  {item.filename}
                </td>
                <td
                  className="cursor-pointer text-[12px] text-[var(--text-secondary)]"
                  onClick={() => onSelect(item.id)}
                  title={categoryDescription(categoryOf(item))}
                >
                  {categoryLabel(categoryOf(item))}
                </td>
                <td
                  className="mono cursor-pointer"
                  onClick={() => onSelect(item.id)}
                >
                  {formatBytes(item.size_bytes)}
                </td>
                <td
                  className="cursor-pointer"
                  onClick={() => onSelect(item.id)}
                >
                  <StatusBadge item={item} />
                </td>
                <td
                  className="cursor-pointer"
                  onClick={() => onSelect(item.id)}
                >
                  <span
                    className="flex items-center gap-1.5 text-[11px] font-medium"
                    style={{ color: crossCheckTone(check).color }}
                  >
                    <IntegrityMark check={check} />
                    <span aria-hidden>
                      {check?.state === "match"
                        ? "Matches custody"
                        : check?.state === "mismatch"
                          ? "Disagrees with custody"
                          : check?.state === "no_stored_hash"
                            ? "No hash on record"
                            : "No custody hash"}
                    </span>
                  </span>
                </td>
                <td
                  className="mono cursor-pointer text-[11px]"
                  onClick={() => onSelect(item.id)}
                  title={item.sha256 || "No hash on record"}
                >
                  {item.sha256 ? shortHash(item.sha256) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="visily-card overflow-hidden">
      <table className="data-table">
        <thead>
          <tr>
            <th className="w-9" />
            <th>Name</th>
            <th>Category</th>
            <th>Size</th>
            <th>Verification</th>
            <th>Integrity</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 8 }).map((_, index) => (
            <tr key={index}>
              <td>
                <Skeleton className="h-3.5 w-3.5" />
              </td>
              <td>
                <Skeleton className="h-3 w-40" />
              </td>
              <td>
                <Skeleton className="h-3 w-20" />
              </td>
              <td>
                <Skeleton className="h-3 w-16" />
              </td>
              <td>
                <Skeleton className="h-4 w-20" />
              </td>
              <td>
                <Skeleton className="h-3 w-28" />
              </td>
              <td>
                <Skeleton className="h-3 w-24" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <span className="sr-only">Loading evidence catalog…</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Empty states                                                        */
/* ------------------------------------------------------------------ */

/**
 * "Nothing acquired" and "nothing matched" are different findings. Collapsing
 * them into one "no data" message lets an examiner conclude a case holds no
 * evidence when in fact a filter is hiding it.
 */
function EmptyState({
  caseId,
  reason,
  onClearFilters,
}: {
  caseId: string;
  reason: "no-evidence" | "no-matches";
  onClearFilters: () => void;
}) {
  if (reason === "no-evidence") {
    return (
      <div className="visily-card flex flex-1 items-center justify-center p-12">
        <div className="max-w-sm text-center">
          <p className="text-[14px] font-medium text-[var(--text-primary)]">
            No evidence acquired in this case
          </p>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Nothing has been acquired or imported against this case yet. This is
            an empty catalog, not a filtered one.
          </p>
          <Button asChild className="mt-4" size="sm">
            <Link to={`/cases/${caseId}/acquire`}>Start acquisition</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="visily-card flex flex-1 items-center justify-center p-12">
      <div className="max-w-sm text-center">
        <p className="text-[14px] font-medium text-[var(--text-primary)]">
          No items match the current filter
        </p>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          This case has evidence — none of it matches the search text and facets
          you have applied.
        </p>
        <Button
          className="mt-4"
          size="sm"
          variant="outline"
          onClick={onClearFilters}
        >
          Clear filters
        </Button>
      </div>
    </div>
  );
}
