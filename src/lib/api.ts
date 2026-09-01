import { getApiBase, resolveApiUrl } from "./apiBase";
import { ApiError } from "./apiError";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBase()}${path}`, init);
  if (!response.ok) {
    let detail = await response.text();
    try {
      const parsed = JSON.parse(detail) as { detail?: string };
      detail = parsed.detail ?? detail;
    } catch {
      // keep raw text
    }
    throw new ApiError(
      response.status,
      detail || `Request failed (${response.status})`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export type CaseRecord = {
  id: string;
  name: string;
  examiner_name: string;
  notes?: string;
  ephemeral?: boolean;
  status?: string;
  created_at: string;
  updated_at?: string;
};

export type VendorHit = {
  vendor: string;
  adapter: string;
  confidence: number;
  markers: string[];
  family?: string;
  capability_tier?: string;
  validation_scope?: string;
  signature_evidence?: string[] | null;
};

export type OemCapability = {
  vendor: string;
  adapter: string;
  capability_tier: string;
  validation_scope: string;
  requires_signature_match?: boolean;
};

export type IdentificationReport = {
  image_size_bytes: number;
  sample_bytes: number;
  hits: VendorHit[];
  filesystem_hints: Array<{ marker: string; label: string }>;
  recommended_adapter: string;
  supported_oems_in_ps: string[];
  oem_capabilities?: OemCapability[];
  coverage_note: string;
};

export type EvidenceRecord = {
  id: string;
  case_id: string;
  filename: string;
  sha256: string;
  md5?: string | null;
  size_bytes: number;
  media_type: string;
  acquired_at: string;
  acquisition_status?: string;
  acquisition_method?: string | null;
  write_blocker?: string | null;
  source_type?: string | null;
  source_identifier?: string | null;
  verification_status?: string;
  identification?: IdentificationReport | null;
  identification_json?: string | null;
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
  device_id?: string | null;
  kind?: string | null;
  status: string;
  vendor: string | null;
  adapter: string | null;
  stats_json: string | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
  progress?: number;
  message?: string;
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
  confidence_tier?: string;
  preview_path: string | null;
  created_at: string;
  timeline_index?: number;
  sequence_on_channel?: number;
  byte_length?: number;
  offset_time_label?: string;
  recorder_start_ts?: string | null;
  recorder_end_ts?: string | null;
  corrected_start_ts?: string | null;
  corrected_end_ts?: string | null;
  timestamp_source?: string | null;
  timestamp_confidence?: number | null;
  offset_order?: number | null;
  deleted_candidate?: boolean;
  codec?: string | null;
  parser_name?: string | null;
  parser_version?: string | null;
  signature_evidence?: Record<string, unknown>;
  validation_evidence?: Record<string, unknown>;
};

export type TimelineChannel = {
  channel: number;
  label: string;
  segment_count: number;
  segments: Segment[];
};

export type Capabilities = {
  ffmpeg_available?: boolean;
  modules: string[];
  recovery_adapters: string[];
  oem_fingerprints: string[];
  hash_algorithms: string[];
  limitations: string[];
};

type VersionResponse = {
  status: string;
  service: string;
  version: string;
  signing_certificate_fingerprint?: string;
  route_count?: number;
  routes_digest?: string;
  capabilities: Capabilities;
};

export type AiFinding = {
  id: string;
  sequence_id: string;
  frame_offset_ms: number;
  finding_type: string;
  label: string | null;
  confidence: number | null;
  bbox?: {
    x?: number;
    y?: number;
    w?: number;
    h?: number;
    detector?: string;
    threshold?: number;
    sample_fps?: number;
    model?: string;
    model_version?: string;
  } | null;
};

export type ImagingDisk = {
  id: string;
  path: string;
  label: string;
  size_bytes: number;
  bus_type: string;
  read_only_capable: boolean;
  requires_admin?: boolean;
};

export type DatasetEntry = {
  id: string;
  purpose?: string;
  present: boolean;
  verified: boolean;
  size_bytes: number;
  license?: string;
  url?: string;
  path?: string;
};

export const api = {
  version: () => request<VersionResponse>("/api/v1/version"),

  health: () =>
    request<VersionResponse>("/api/v1/version").then((v) => ({
      status: v.status,
      service: v.service,
      version: v.version,
    })),

  capabilities: () =>
    request<VersionResponse>("/api/v1/version").then((v) => v.capabilities),

  listCases: () => request<CaseRecord[]>("/api/v1/cases"),

  listCaseRegistry: () =>
    request<
      Array<
        CaseRecord & {
          evidence_count: number;
          total_bytes: number;
          recovery_jobs: number;
        }
      >
    >("/api/v1/cases/registry"),

  createCase: (
    body: { name: string; examiner_name: string; notes?: string },
    options?: { ephemeral?: boolean },
  ) =>
    request<CaseRecord>("/api/v1/cases", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(options?.ephemeral ? { "X-Pramaan-Ephemeral": "1" } : {}),
      },
      body: JSON.stringify(body),
    }),

  deleteCase: (caseId: string) =>
    request<void>(`/api/v1/cases/${caseId}`, { method: "DELETE" }),

  deleteEphemeralCases: () =>
    request<void>("/api/v1/cases/ephemeral", { method: "DELETE" }),

  signingHistory: () =>
    request<{
      active_fingerprint: string;
      entries: Array<{
        label: string;
        fingerprint: string;
        generated_at: string;
        storage_backend: string;
        active: boolean;
      }>;
    }>("/api/v1/signing/history"),

  getCase: (caseId: string) =>
    request<{
      case: CaseRecord;
      evidence: EvidenceRecord[];
      jobs: RecoveryJob[];
      custody: CustodyEvent[];
      chain: {
        ok: boolean;
        intact: boolean;
        first_broken_row_id: number | null;
        tip_hash?: string | null;
      };
    }>(`/api/v1/cases/${caseId}/workspace`),

  acquire: (caseId: string, actor: string, file: File) => {
    const form = new FormData();
    form.append("actor", actor);
    form.append("file", file);
    return request<{
      evidence: EvidenceRecord;
      identification: IdentificationReport;
      vendor_hints: VendorHit[];
    }>(`/api/v1/cases/${caseId}/devices/acquire`, {
      method: "POST",
      body: form,
    });
  },

  createLabSpecimen: (
    caseId: string,
    actor: string,
    vendor: "dahua" | "honeywell" | "hikvision" = "dahua",
  ) =>
    request<{
      evidence: EvidenceRecord;
      identification: IdentificationReport;
      vendor?: string;
      specimen_type?: string;
    }>(`/api/v1/cases/${caseId}/devices/acquire/synthetic`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor, source: "synthetic_specimen", vendor }),
    }),

  listImagingDisks: () =>
    request<{ disks: ImagingDisk[]; count: number; read_only_policy: string }>(
      "/api/v1/acquisition/disks",
    ),

  listResumableAcquisitions: (caseId: string) =>
    request<{ case_id: string; devices: Array<Record<string, unknown>> }>(
      `/api/v1/cases/${caseId}/acquisition/resumable`,
    ),

  acquirePhysical: (
    caseId: string,
    body: {
      actor: string;
      source_path: string;
      source_type?: "file" | "physical" | "e01";
      max_bytes?: number;
    },
  ) =>
    request<{
      job: {
        id: string;
        case_id: string;
        device_id: string;
        status: string;
        kind: string;
      };
      device: Record<string, unknown>;
      poll_url: string;
      events_url: string;
    }>(`/api/v1/cases/${caseId}/devices/acquire/physical`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  resumeAcquisition: (deviceId: string, actor: string) =>
    request<{ job: { id: string }; poll_url: string; events_url: string }>(
      `/api/v1/devices/${deviceId}/acquire/resume`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor }),
      },
    ),

  listOemImages: () =>
    request<{
      env_var: string;
      configured: boolean;
      label: string;
      images: Array<{ filename: string; size_bytes: number }>;
      count: number;
    }>("/api/v1/acquisition/oem-images"),

  acquireOemImage: (caseId: string, actor: string, filename: string) =>
    request<{
      evidence: EvidenceRecord;
      identification: IdentificationReport;
      source: string;
    }>(`/api/v1/cases/${caseId}/devices/acquire/oem`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor, filename }),
    }),

  acquireLogical: (
    caseId: string,
    body: {
      actor: string;
      host: string;
      port?: number;
      scheme?: "http" | "https";
      user: string;
      password: string;
      vendor?: "hikvision" | "dahua";
      max_clips?: number;
    },
  ) =>
    request<{
      case_id: string;
      host: string;
      vendor: string;
      clips_acquired: number;
      devices: Array<{
        evidence: EvidenceRecord;
        remote_path: string;
        logical_only: boolean;
      }>;
      note: string;
    }>(`/api/v1/cases/${caseId}/devices/acquire/logical`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  calibrateDrift: (
    deviceId: string,
    referenceWallUnix: number,
    referenceDeviceUnix: number,
  ) =>
    request<{ device_id: string; drift_offset_seconds: number; note: string }>(
      `/api/v1/devices/${deviceId}/drift-calibration`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reference_wall_unix: referenceWallUnix,
          reference_device_unix: referenceDeviceUnix,
        }),
      },
    ),

  exportCase: async (caseId: string, actor: string) => {
    const form = new FormData();
    form.append("actor", actor);
    const response = await fetch(
      `${getApiBase()}/api/v1/cases/${caseId}/export`,
      { method: "POST", body: form },
    );
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || "Export failed");
    }
    return response.json() as Promise<{
      case_id: string;
      filename: string;
      download_url: string;
      size_bytes: number;
    }>;
  },

  importCase: async (actor: string, file: File) => {
    const form = new FormData();
    form.append("actor", actor);
    form.append("bundle", file);
    const response = await fetch(`${getApiBase()}/api/v1/cases/import`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || "Import failed");
    }
    return response.json() as Promise<{
      case_id: string;
      files_verified: number;
      integrity_ok: boolean;
      signer_fingerprint: string;
    }>;
  },

  runAiAnalytics: (deviceId: string, actor: string) =>
    request<{
      job: { id: string; status: string; kind: string };
      poll_url: string;
      events_url: string;
    }>(`/api/v1/devices/${deviceId}/ai-analytics`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor }),
    }),

  listAiFindings: (deviceId: string) =>
    request<{ device_id: string; findings: AiFinding[]; count: number }>(
      `/api/v1/devices/${deviceId}/ai-findings`,
    ),

  identify: (imageId: string) =>
    request<IdentificationReport>(`/api/v1/devices/${imageId}/identification`, {
      method: "POST",
    }),

  readDeviceBytes: (deviceId: string, offset = 0, length = 256) =>
    request<{
      device_id: string;
      offset: number;
      length: number;
      file_size: number;
      hex: string;
      ascii: string;
    }>(`/api/v1/devices/${deviceId}/bytes?offset=${offset}&length=${length}`),

  deviceStructure: (deviceId: string) =>
    request<{
      device_id: string;
      size_bytes: number;
      nodes: Array<{
        label: string;
        offset: number;
        size: number;
        type: string;
        meta?: Record<string, unknown>;
        children: Array<{
          label: string;
          offset: number;
          size: number;
          type: string;
          meta?: Record<string, unknown>;
          children: unknown[];
        }>;
      }>;
    }>(`/api/v1/devices/${deviceId}/structure`),

  recover: (
    _caseId: string,
    imageId: string,
    actor: string,
    adapter?: string,
  ) =>
    request<{ job: RecoveryJob; status: string; poll_url: string }>(
      `/api/v1/devices/${imageId}/recover`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor, adapter: adapter || undefined }),
      },
    ),

  getJob: (jobId: string) =>
    request<{
      job: RecoveryJob;
      segments: Segment[];
      progress?: number;
      message?: string;
    }>(`/api/v1/jobs/${jobId}`),

  getJobStatus: (jobId: string) =>
    request<{
      status: string;
      progress?: number;
      message?: string | null;
      error?: string | null;
      result?: {
        demo_mode_unavailable?: boolean;
        message?: string;
        findings_count?: number;
      } | null;
    }>(`/api/v1/jobs/${jobId}/status`),

  listDeviceSegments: (deviceId: string) =>
    request<{ device_id: string; segments: Segment[] }>(
      `/api/v1/devices/${deviceId}/sequences`,
    ),

  getTimeline: (caseId: string, deviceId: string) =>
    request<{
      job_id: string;
      total_segments: number;
      channel_count: number;
      channels: TimelineChannel[];
      normalization: { method: string; rtc_parsed: boolean; note: string };
    }>(`/api/v1/cases/${caseId}/timeline/${deviceId}`),

  custody: (caseId: string) =>
    request<{
      custody: CustodyEvent[];
      chain: {
        ok: boolean;
        intact: boolean;
        first_broken_row_id: number | null;
        tip_hash?: string | null;
      };
    }>(`/api/v1/cases/${caseId}/workspace`).then((w) => ({
      events: w.custody,
      chain: w.chain,
    })),

  custodyStatus: (caseId: string) =>
    request<{
      intact: boolean;
      first_broken_row_id: number | null;
      tip_hash?: string | null;
    }>(`/api/v1/cases/${caseId}/custody-log/status`),

  cancelJob: (jobId: string) =>
    request<{ id: string; status: string }>(`/api/v1/jobs/${jobId}/cancel`, {
      method: "POST",
    }),

  integrityReport: (caseId: string) =>
    request<Record<string, unknown>>(
      `/api/v1/cases/${caseId}/report/integrity`,
    ),

  integrityReportHtmlUrl: (caseId: string) =>
    resolveApiUrl(`/api/v1/cases/${caseId}/report/integrity.html`),

  integrityReportPdfUrl: (caseId: string) =>
    resolveApiUrl(`/api/v1/cases/${caseId}/report/integrity.pdf`),

  report: (caseId: string) =>
    request<Record<string, unknown>>(`/api/v1/cases/${caseId}/report`),

  reportHtmlUrl: (caseId: string) =>
    resolveApiUrl(`/api/v1/cases/${caseId}/report.html`),

  reportPdfUrl: (caseId: string) =>
    resolveApiUrl(`/api/v1/cases/${caseId}/report.pdf`),

  verify: (imageId: string) =>
    request<{
      ok: boolean;
      expected_sha256?: string;
      actual_sha256?: string;
      expected_md5?: string;
      actual_md5?: string;
      sha256_ok?: boolean;
      md5_ok?: boolean;
    }>(`/api/v1/devices/${imageId}/verify`),

  exportSegment: (deviceId: string, segmentId: string) =>
    request<{ filename: string; download_url: string; media_type: string }>(
      `/api/v1/devices/${deviceId}/sequences/${segmentId}/export`,
      { method: "POST" },
    ),

  getSettings: () =>
    request<{
      working_directory: string;
      signing_certificate_fingerprint: string;
    }>("/api/v1/settings"),

  updateSettings: (body: { working_directory: string }) =>
    request<{
      working_directory: string;
      signing_certificate_fingerprint: string;
    }>("/api/v1/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  runToolVerification: () =>
    request<{ job_id: string }>("/api/v1/tool-verification/run", {
      method: "POST",
    }),

  acquisitionCapabilities: () =>
    request<{
      chunked_imaging: boolean;
      checkpoint_resume: boolean;
      bad_sector_zero_fill: boolean;
      e01_input: boolean;
      physical_disks: boolean;
      logical_network: boolean;
      oem_drop_zone_env: string;
      oem_drop_zone_label: string;
      oem_drop_zone_configured: boolean;
    }>("/api/v1/acquisition/capabilities"),

  listToolVerificationResults: () =>
    request<
      Array<{
        id: string;
        run_at: string;
        app_version: string;
        passed: number;
        results: {
          stages: Array<{ stage: string; passed: boolean; detail: string }>;
          passed: boolean;
          app_version: string;
          vendors_verified: string[];
        };
      }>
    >("/api/v1/tool-verification/results"),

  toolVerificationHtmlUrl: (runId: string) =>
    resolveApiUrl(`/api/v1/tool-verification/results/${runId}/report.html`),

  toolVerificationPdfUrl: (runId: string) =>
    resolveApiUrl(`/api/v1/tool-verification/results/${runId}/report.pdf`),

  listDatasets: () => request<DatasetEntry[]>("/api/v1/datasets"),

  fetchDataset: (datasetId: string) =>
    request<{ job_id: string; dataset_id: string; status: string }>(
      `/api/v1/datasets/${encodeURIComponent(datasetId)}/fetch`,
      { method: "POST" },
    ),
};
