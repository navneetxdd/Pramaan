# Changelog

All notable changes to Forensic Workstation (SIH26150) follow [Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-09-01

### Added (M5 — Case export/import + AI analytics)

- **Signed case bundles** (`.pramaan.zip`): manifest + RSA-PSS signature, per-file SHA-256, custody/sequences/AI findings.
- `POST /api/v1/cases/{id}/export`, `POST /api/v1/cases/import`, `GET /api/v1/bundles/{filename}`.
- Import re-verifies all hashes and device integrity on the target workstation.
- **AI analytics job**: 1 fps motion sampling (ffmpeg scene detect + stream fallback), optional OpenCV Haar face candidates.
- `POST /api/v1/devices/{id}/ai-analytics`, `GET /api/v1/devices/{id}/ai-findings`.
- Timeline includes AI finding markers; AI Analytics page with mandatory investigative-leads banner.
- Cases dashboard: import bundle; case overview: export bundle.
- Tests: export/import roundtrip + AI API (`engine/tests/test_m5_case_transfer.py`).

### Verified

- 30/30 engine unit tests passing.
- M1–M4 smoke flow: 26/26 API steps passing.
- Frontend build succeeds.

## [0.5.0] - 2026-09-01

### Added (M4 — Physical acquisition)

- **Chunked block imaging** with read-only source opens, bad-sector zero-fill + map, checkpoint/resume (`acquisition_checkpoints`).
- Windows disk enumeration via PowerShell (`GET /api/v1/acquisition/disks`); Unix via `lsblk`.
- Physical imaging job API: `POST .../devices/acquire/physical`, `POST /devices/{id}/acquire/resume` with SSE progress.
- Optional **E01 input** when `pyewf` is installed (`engine/app/services/e01_reader.py`).
- **Drift calibration** API: `POST /api/v1/devices/{id}/drift-calibration` + timeline UI panel.
- Acquire UI: disk picker, block imaging path, resumable acquisitions, read-only policy banner.
- Acquisition reconciliation on engine restart (in-flight → `interrupted`).
- Tests: file imaging E2E, checkpoint resume, API smoke (`engine/tests/test_m4_acquisition.py`).

### Changed

- `register_pending_device` for pre-hash imaging rows; integrity verify returns `hash_pending` until complete.
- Version bump script now syncs `engine/app/core/config.py` `APP_VERSION`.

### Verified

- 26/26 engine unit tests passing.
- Frontend `npm run build` succeeds.

## [0.4.0] - 2026-09-01

### Added (M3 — Honeywell + Tier 2 filesystem)

- **Honeywell G.3.3 parser**: GPT/sector-34 layout, partition header, channel-index recovery (expiration deletion), raw video-region NAL scan (format deletion).
- Honeywell lab specimen generator (`engine/app/verification/honeywell_specimen.py`).
- **`generic_tier2` adapter**: pytsk3 filesystem undelete with manual FAT deleted-entry fallback + H.264 carve degradation.
- OEM routing: Honeywell → `honeywell`; TP-Link/Godrej/Matrix → `generic_tier2`.
- Golden tests: Honeywell both deletion mechanisms + FAT deleted-file recovery (`engine/tests/test_m3_parsers.py`).

### Changed

- `pytsk3` added to engine requirements (Windows wheel verified).
- `/api/v1/version` limitations reflect Tier 2 degradation messaging.

### Verified

- 20/20 engine unit tests passing.
- Tool Verification Suite still passes.

## [0.3.0] - 2026-09-01

### Added (M2 — Parser depth & engine correctness)

- `construct` schemas for Dahua DHAV and Hikvision HKVI with **4-check validation** (header, footer/trailer, size consistency, checksum).
- Golden-file parser tests (`engine/tests/test_m2_parsers.py`).
- PAdES signing certificate/key **persisted** under `{working_dir}/signing/` across engine restarts.
- Job reconciliation on startup: stale `running`/`pending` jobs → `interrupted`.
- Persisted job API fallback after restart (`GET /jobs/{id}`, SSE terminal events).
- Recovery UI: confidence ring + badges driven by `validation_level` / `confidence_tier`.

### Changed

- Lab specimen DHAV frames now include valid checksum bytes (4-check compatible).
- Dahua/Hikvision adapters use schema validators instead of raw heuristic length probes.

### Verified

- 14/14 engine unit tests passing (includes signing persistence + job reconciliation).
- Tool Verification Suite passes with updated specimen format.

## [0.2.0] - 2026-09-01

### Added

- Unified forensic engine replacing dual backend/engine split for all `/api/*` routes.
- Migrated parsers: Dahua DHAV, Hikvision HKVI, H.264 carve, Honeywell GPT-aware carve.
- Adaptive temporal sequencing (Part G.5) wired into recovery pipeline.
- Manufacturer detection (Layer 1) for 8 OEM profiles + filesystem markers.
- PAdES B-B PDF report signing via ReportLab + pyHanko with custody-chain gate (409 on broken chain).
- Tool Verification Suite with passing automated self-test (`engine/tests/test_tool_verification.py`).
- Legacy compatibility API removed; frontend uses `/api/v1/*` only.
- Status bar: engine version, live custody verification dot for active case.
- GitHub Actions CI: engine tests + frontend build matrix (Linux).

### Verified

- End-to-end: case → lab specimen → recovery → 2+ sequences → custody intact.
- 5 engine unit tests passing.

## [0.1.0] - 2026-09-01

### Added

- `/DESIGN.md` — Part K design system (instrumentation aesthetic, single source of visual truth).
- `/DEVIATIONS.md` — documented gaps between repository state and Master Build Prompt v1.0.
- `/engine/` — Python forensic engine scaffold per Part D:
  - Part F SQLite schema in `engine/app/core/db.py`
  - Hash-chained `custody_log` with GENESIS seed and verification
  - Outbound socket guard (localhost only) at engine startup
  - `/api/v1/cases` CRUD with nested devices and custody-log endpoints
  - `/api/v1/jobs/{id}` and SSE progress stream scaffold
- Legacy `/api/*` routes remain mounted for existing UI until migration completes.

### Changed (M0)

- Repo layout: `/src`, `/src-tauri`, root `package.json` per Part D.
- Deleted `backend/pramaan/`; engine is the sole backend.
- FastAPI no longer serves SPA; Tauri loads Vite dev server / bundled `dist`.
- `GET /api/v1/version` — single version + capabilities endpoint.
- Version bump script: `npm run version:bump -- <semver>`.
- CI matrix: engine tests on ubuntu/windows/macos; frontend build at repo root.
- Removed unused `@fontsource-variable/geist` dependency.

### Known limitations (post-M0)

- UI skeleton still pre-M1 (global routes, KPI cards, no shadcn/SSE wiring).
