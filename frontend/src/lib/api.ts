const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export type CaseRecord = {
  id: string;
  title: string;
  examiner: string;
  reference: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type EvidenceRecord = {
  id: string;
  case_id: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  acquired_at: string;
};

export type CustodyEvent = {
  id: number;
  case_id: string;
  image_id: string | null;
  actor: string;
  action: string;
  detail: string | null;
  created_at: string;
};

export type RecoveryJob = {
  id: string;
  case_id: string;
  image_id: string;
  status: string;
  vendor: string | null;
  adapter: string | null;
  stats_json: string | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
};

export type Segment = {
  id: string;
  job_id: string;
  channel: number | null;
  vendor: string;
  offset_start: number;
  offset_end: number;
  frame_count: number;
  confidence: number;
  validation: string;
  preview_path: string | null;
  created_at: string;
};

export const api = {
  health: () => request<{ status: string; service: string }>("/api/health"),

  listCases: () => request<{ cases: CaseRecord[] }>("/api/cases"),

  createCase: (body: { title: string; examiner: string; reference?: string }) =>
    request<{ case: CaseRecord }>("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getCase: (caseId: string) =>
    request<{
      case: CaseRecord;
      evidence: EvidenceRecord[];
      jobs: RecoveryJob[];
      custody: CustodyEvent[];
    }>(`/api/cases/${caseId}`),

  acquire: (caseId: string, actor: string, file: File) => {
    const form = new FormData();
    form.append("actor", actor);
    form.append("file", file);
    return request<{ evidence: EvidenceRecord; vendor_hints: unknown[] }>(
      `/api/cases/${caseId}/acquire`,
      { method: "POST", body: form },
    );
  },

  recover: (caseId: string, imageId: string, actor: string) =>
    request<{ job: RecoveryJob; status: string; poll_url: string }>(
      `/api/cases/${caseId}/evidence/${imageId}/recover`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor }),
      },
    ),

  getJob: (jobId: string) =>
    request<{ job: RecoveryJob; segments: Segment[] }>(`/api/jobs/${jobId}`),

  custody: (caseId: string) =>
    request<{ events: CustodyEvent[]; chain: { ok: boolean } }>(`/api/cases/${caseId}/custody`),

  report: (caseId: string) => request<Record<string, unknown>>(`/api/cases/${caseId}/report`),

  reportHtmlUrl: (caseId: string) => `/api/cases/${caseId}/report.html`,

  verify: (imageId: string) =>
    request<{ ok: boolean; expected?: string; actual?: string }>(`/api/evidence/${imageId}/verify`),

  exportSegment: (jobId: string, segmentId: string) =>
    request<{ filename: string; download_url: string }>(
      `/api/jobs/${jobId}/segments/${segmentId}/export`,
      { method: "POST" },
    ),
};
