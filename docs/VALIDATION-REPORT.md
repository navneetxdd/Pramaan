# Validation report

## Record

- Product: Pramaan 0.6.0
- Date: 1 September 2026
- Environment: Windows 10.0.26200, Python 3.13, repository workspace `C:\Users\navne\Desktop\SAH`
- Scope: committed automated engine tests, generated validation assets, and production frontend compilation
- Excluded: real OEM disks, hardware write blockers, damaged media, RAID, encrypted stores, installer signing, deployment on a clean forensic workstation, legal admissibility, and performance at disk scale

Version evidence: `package.json`, `engine/app/__init__.py`, `engine/app/core/config.py`, and `src-tauri/tauri.conf.json` all record `0.6.0`.

## Commands and recorded results

### Engine suite

```powershell
python -m pytest engine/tests -q
```

Recorded result (1 September 2026, integrated release gate):

```text
50 passed, 1 skipped in ~22s
```

The skipped case was `test_oem_image_dir_when_present`: `No OEM images in drop zone`. Warnings observed were a ReportLab Python 3.14 deprecation warning and fallback from unavailable OS credential storage to a restricted signing-key file in signing persistence tests.

### Frontend production build

```powershell
npx tsc --noEmit
npm run build
python scripts/smoke_test.py
```

Recorded result:

```text
vite v5.4.19 — built successfully
smoke_test.py — Passed: 42/42
```

Warnings observed: six-month-old Browserslist data and a Tauri dialog module imported both statically and dynamically. Neither warning failed compilation.

## What the suite demonstrates

| Area | Evidence demonstrated | Test source |
|---|---|---|
| Adapter routing | generated Dahua, Hikvision, and Honeywell specimens select expected adapters | `engine/tests/test_adapter_routing.py` |
| Dahua parser | generated DHAV records pass four checks and recover segments | `engine/tests/test_m2_parsers.py` |
| Hikvision parser | generated sealed HKVI blocks pass four checks; generated end-to-end flow completes | `engine/tests/test_m2_parsers.py`, `engine/tests/test_e2e_hikvision.py` |
| Honeywell parser | generated layout, NAL headers, expiration and format-deletion paths recover candidates | `engine/tests/test_m3_parsers.py`, `engine/tests/test_e2e_honeywell.py` |
| Generic filesystem | generated FAT16 deleted-entry fixture returns recovery output with `pytsk3` available | `engine/tests/test_m3_parsers.py`, `engine/tests/test_validation_assets.py` |
| Acquisition | file-source copy, checkpoint, resume, hashes, integrity, API start, enumeration, and drift endpoint | `engine/tests/test_m4_acquisition.py` |
| Custody and cases | create/list/get/delete and hash-chain integrity | `engine/tests/test_v1_cases.py` |
| Signing | certificate persistence and signed PDF path | `engine/tests/test_signing_persistence.py` |
| Transfer security | export/import round trip, embedded-certificate verification, tamper rejection, and traversal rejection | `engine/tests/test_m5_case_transfer.py`, `engine/tests/test_case_bundle_security.py` |
| Restart handling | active jobs reconcile to interrupted | `engine/tests/test_job_reconciliation.py` |
| Built-in verification | nine or more generated-fixture stages across three parser families; signed HTML/PDF export | `engine/tests/test_tool_verification.py`, `engine/tests/test_tool_verification_export.py` |
| Custody evidence binding | SHA-256 digests bound into custody hash on acquire and segment artifact creation | `engine/tests/test_custody_evidence_binding.py` |
| Integrity reports | Standard reports reject broken chains (409); integrity endpoints document breaks | `engine/tests/test_custody_evidence_binding.py`, `engine/tests/test_report_custody_gate.py` |
| Dahua timestamps | Lab DHAV frames carry recorder Unix timestamps surfaced on timeline | `engine/tests/test_m2_parsers.py` |
| Analytics (CAVIAR Walk1) | person object precision 1.0 recall 0.2917; foreground motion precision 0.9231 recall 0.6667; face/scene counts only | `validation_data/results/analytics_validation.json`, `scripts/validate_analytics.py` |

## Validation assets

`validation_data/manifest.json` records generated Dahua, Hikvision, Honeywell, and FAT16 files with byte sizes and SHA-256 values. It also records downloaded narrative files, YOLOX Nano (Apache-2.0), CAVIAR Walk1 video/ground truth, and optional face model paths. The manifest's `oem_files` array is empty — no independent recorder disks were available.

`validation_data/results/analytics_validation.json` records CAVIAR Walk1 event-level metrics for person-object and foreground-motion pipelines on a single public clip.

Generated known-answer data is useful for regression and code-path verification. It cannot establish behavior on independent recorder media, real deletion patterns, fragmentation, firmware variants, encryption, disk damage, or adversarial input.

## Result and release meaning

The tested source revision passed its local engine suite and frontend compilation in the recorded environment. This supports a demonstration release against committed generated fixtures. It does not support a claim of field validation for any real OEM disk.

## Reproduction controls still required

For a formal validation package, record the source revision identifier, clean-environment dependency installation, exact OS and tool versions, test stdout/stderr, fixture hashes recomputed independently, installer hash/signature, hardware inventory, operator identity, and retained output artifacts. This workspace was not detected as a Git repository during this documentation run, so no commit identifier is available in this report.
