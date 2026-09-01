# Architecture, data flow, and trust boundaries

## Deployed shape

Pramaan 0.6.0 is a local desktop application: a React/Vite interface is bundled in a Tauri 2 shell, which communicates with a FastAPI engine on loopback. The engine stores metadata in SQLite and case artifacts below `FORENSIC_WORKSTATION_DATA` (default `~/ForensicWorkstation/data`).

```text
Examiner
  │
  ▼
Tauri window ── React UI
  │ HTTP /api/v1 on 127.0.0.1:8787
  ▼
FastAPI engine
  ├── acquisition and SHA-256/MD5 verification
  ├── OEM detection and recovery adapters
  ├── timeline, export, reports, and signing
  └── SQLite custody and job records
       │
       ├── cases/<case-id>/ evidence and recovered artifacts
       ├── reports/
       ├── bundles/
       └── signing/
```

Evidence: `src-tauri/tauri.conf.json`, `engine/app/main.py`, `engine/app/core/config.py`, `engine/app/core/db.py`, and `README.md`.

## Evidence data flow

1. The examiner creates a case; SQLite records the case and first custody event.
2. Acquisition opens a file, raw device, or optional E01 input read-only, copies data to raw DD, calculates MD5 and SHA-256, writes a SHA-256 sidecar, records unreadable sector offsets, and rehashes the destination.
3. Manufacturer detection scans at most the first 64 MiB for byte markers and selects the highest-scoring adapter. A brand name alone is not proof of an internal storage family.
4. The selected adapter scans the acquired image. Dahua DHAV, Hikvision HKVI, and Honeywell structures have dedicated generated-fixture paths; other listed brands use filesystem recovery or generic H.264 carving.
5. Recovered candidates become offset-ordered sequences. Current recovery sequencing assigns synthetic `T+offset` labels; wall-clock meaning requires independent corroboration.
6. JSON, HTML, and signed PDF reports are generated only when the custody hash chain verifies.
7. Case transfer creates a ZIP containing a signed manifest, embedded certificate, per-file SHA-256 values, evidence, sequences, custody rows, and analytics rows. Import rejects unsafe paths and hash or signature mismatches.

Evidence: `engine/app/services/physical_imaging.py`, `engine/app/parsers/manufacturer_detect.py`, `engine/app/services/recovery.py`, `engine/app/services/reporting.py`, and `engine/app/services/case_bundle.py`.

## Trust boundaries

| Boundary | Trusted side | Untrusted input | Control present | Residual risk |
|---|---|---|---|---|
| Recorder media → acquisition | examiner workstation | malformed media, read errors, deceptive labels | read-only open, destination rehash, bad-sector map | software read-only access is not a hardware write blocker |
| UI → local API | loopback process | local browser/webview requests | API bound to local service design; Tauri CSP limits origins | another local process may attempt loopback access; no user authentication is documented |
| Image → parser | engine process | attacker-controlled bytes and sizes | bounded detection sample; parser checks; background job error handling | parser defects or resource exhaustion remain possible |
| Case bundle → importer | case workspace | crafted ZIP and manifest | traversal, symlink, entry-count, free-space, signature, and SHA-256 checks | a signed bundle identifies its embedded key, not an external trust authority |
| SQLite/artifact store → report | report generator | altered database or files | device rehash and custody-chain verification | host administrator can alter files, database, application, and signing material |
| Signing key → verifier | OS credential store or restricted file | key theft or substitution | persisted RSA key, certificate fingerprint, PAdES/manifest signatures | self-signed certificate does not establish institutional identity or trusted time |
| External tools/models | configured executable/model path | substituted binary or model | paths are configurable | no packaged provenance attestation is evidenced |

Evidence: `src-tauri/capabilities/default.json`, `engine/app/core/signing.py`, `engine/app/services/case_bundle.py`, `engine/tests/test_case_bundle_security.py`, and `engine/app/core/config.py`.

## Security posture boundaries

- The application does not decrypt encrypted stores and does not reconstruct RAID.
- Tauri permits file reads and shell-open operations for the main window; these permissions increase the consequence of a renderer compromise.
- The content-security policy permits inline script and style. This is a release-hardening concern, not proof of an exploitable issue.
- Custody chaining detects later row modification when verified; it does not independently prove the actor's identity or prevent deletion by a privileged host user.

Evidence: `engine/app/api/v1/version.py`, `src-tauri/capabilities/default.json`, `src-tauri/tauri.conf.json`, and `engine/app/core/db.py`.
