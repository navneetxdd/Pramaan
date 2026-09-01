const RECENT_KEY = "pramaan.recentCases";

export function loadRecentCaseIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

export function pushRecentCase(caseId: string) {
  const next = [caseId, ...loadRecentCaseIds().filter((id) => id !== caseId)].slice(0, 5);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

export function mostRecentCaseId(): string | null {
  return loadRecentCaseIds()[0] ?? null;
}
