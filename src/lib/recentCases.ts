const RECENT_KEY = "pramaan.recentCases";

export function loadRecentCaseIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

export function pushRecentCase(caseId: string) {
  const next = [
    caseId,
    ...loadRecentCaseIds().filter((id) => id !== caseId),
  ].slice(0, 5);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

export function mostRecentCaseId(): string | null {
  return loadRecentCaseIds()[0] ?? null;
}

export function removeRecentCase(caseId: string) {
  const next = loadRecentCaseIds().filter((id) => id !== caseId);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

export function pruneRecentCases(validIds: Iterable<string>) {
  const valid = new Set(validIds);
  const pruned = loadRecentCaseIds().filter((id) => valid.has(id));
  localStorage.setItem(RECENT_KEY, JSON.stringify(pruned));
}
