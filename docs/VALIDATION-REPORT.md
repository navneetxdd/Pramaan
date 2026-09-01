# Validation report

## Record

- Product: Pramaan 0.6.0
- Date: 1 September 2026
- Environment: Windows 10.0.26200, Python 3.13, repository workspace `C:\Users\navne\Desktop\SAH`
- Scope: committed automated engine tests, public corpora (Digital Corpora), generated validation assets, smoke API walkthrough, and production frontend compilation
- Excluded: real Dahua/Hikvision/Honeywell DVR OEM disks (none exist in public corpora), hardware write blockers, damaged media, RAID, encrypted stores, installer signing, deployment on a clean forensic workstation, legal admissibility, and performance at disk scale

Version evidence: `package.json`, `engine/app/__init__.py`, `engine/app/core/config.py`, and `src-tauri/tauri.conf.json` all record `0.6.0`.

## Commands and recorded results

### Engine suite

```powershell
python -m pytest engine/tests -q
python scripts/verify_p0.py
```

Recorded result (1 September 2026, integrated release gate):

```text
60 passed in ~50s
verify_p0.py — 15/15 ALL PASS
```

### Public media OEM pipeline

```powershell
python scripts/fetch_validation_assets.py --real-fs
python scripts/test_public_media.py
```

Recorded result:

```text
OEM drop zone: nps-2009-canon2-gen6.E01 (Digital Corpora NIST camera-card E01, ~31 MB)
                 fat16_deleted_entry.img (generated tier-2 deleted-entry fixture)
test_public_media.py — PASS (operator_oem_image acquisition, verify, identify, recover)
```

**Important:** No authoritative public Dahua/Hikvision/Honeywell DVR disk images exist on Digital Corpora or CFReDS. The canon2 E01 validates E01 ingest and OEM drop-zone acquisition; it is not a surveillance DVR specimen.

### Frontend production build

```powershell
npx tsc --noEmit
npm run build
python scripts/smoke_test.py
```

Recorded result:

```text
tsc — clean
vite v5.4.19 — built successfully
smoke_test.py — Passed: 41/42 (intermittent ephemeral cleanup flake on one smoke case)
```

Honeywell analytics smoke path uses recovered specimen slices with embedded CAVIAR access units (SPS+PPS+IDR). When slices cannot be decoded, analytics completes with `demo_mode_unavailable` — no substitute reference stream is injected.

## What the suite demonstrates

| Area | Evidence demonstrated | Test source |
|---|---|---|
| Adapter routing | generated Dahua, Hikvision, and Honeywell specimens select expected adapters | `engine/tests/test_adapter_routing.py` |
| Dahua parser | generated DHAV records pass four checks and recover segments | `engine/tests/test_m2_parsers.py` |
| Hikvision parser | generated sealed HKVI blocks pass four checks; generated end-to-end flow completes | `engine/tests/test_m2_parsers.py`, `engine/tests/test_e2e_hikvision.py` |
| Honeywell parser | generated layout, NAL headers, expiration and format-deletion paths recover candidates | `engine/tests/test_m3_parsers.py`, `engine/tests/test_e2e_honeywell.py` |
| Generic filesystem | generated FAT16 deleted-entry fixture returns recovery output with `pytsk3` available | `engine/tests/test_m3_parsers.py`, `engine/tests/test_validation_assets.py` |
| Real filesystem OEM | public E01 + tier-2 FAT fixture in OEM drop zone; acquire/verify/recover via API | `scripts/test_public_media.py`, `engine/tests/test_real_fs_recovery.py` |
| Acquisition | file-source copy, checkpoint, resume, hashes, integrity, API start, enumeration, and drift endpoint | `engine/tests/test_m4_acquisition.py` |
| Custody and cases | create/list/get/delete and hash-chain integrity | `engine/tests/test_v1_cases.py` |
| Signing | certificate persistence and signed PDF path | `engine/tests/test_signing_persistence.py` |
| Transfer security | export/import round trip, embedded-certificate verification, tamper rejection, and traversal rejection | `engine/tests/test_m5_case_transfer.py`, `engine/tests/test_case_bundle_security.py` |
| Restart handling | active jobs reconcile to interrupted | `engine/tests/test_job_reconciliation.py` |
| Built-in verification | nine or more generated-fixture stages across three parser families; signed HTML/PDF export | `engine/tests/test_tool_verification.py`, `engine/tests/test_tool_verification_export.py` |
| Custody evidence binding | SHA-256 digests bound into custody hash on acquire and segment artifact creation | `engine/tests/test_custody_evidence_binding.py` |
| Integrity reports | Standard reports reject broken chains (409); integrity endpoints document breaks | `engine/tests/test_custody_evidence_binding.py`, `engine/tests/test_report_custody_gate.py` |
| Dahua timestamps | Lab DHAV frames carry recorder Unix timestamps via extension TLV `0x72` surfaced on timeline | `engine/tests/test_m2_parsers.py` |
| Hikvision timestamps | Lab HKVI blocks carry block epoch surfaced on timeline | `engine/tests/test_e2e_hikvision.py` |
| Logical network acquisition | Hikvision ISAPI index/download against mocked HTTP fixture | `engine/tests/test_logical_acquisition.py` |
| Honeywell analytics e2e | Recovered Honeywell specimen produces motion/object/face leads from carved access units when OpenCV present | `engine/tests/test_caviar_analytics.py` |
| Analytics (CAVIAR Walk1) | person object precision 1.0 recall 0.2917; foreground motion precision 0.9231 recall 0.6667; face/scene counts only | `validation_data/results/analytics_validation.json`, `scripts/validate_analytics.py` |

## Validation assets

`validation_data/manifest.json` records generated Dahua, Hikvision, Honeywell, and FAT16 files with byte sizes and SHA-256 values. It also records downloaded narrative files, Digital Corpora `nps-2009-canon2-gen6.E01`, YOLOX Nano (Apache-2.0), CAVIAR Walk1 video/ground truth, and optional face model paths.

`validation_data/oem/` is populated by `fetch_validation_assets.py --real-fs` with the canon2 E01 and the tier-2 FAT16 deleted-entry image for OEM acquire UI testing.

`validation_data/results/analytics_validation.json` records CAVIAR Walk1 event-level metrics for person-object and foreground-motion pipelines on a single public clip.

Generated known-answer data is useful for regression and code-path verification. It cannot establish behavior on independent recorder media, real deletion patterns, fragmentation, firmware variants, encryption, disk damage, or adversarial input.

## Result and release meaning

The tested source revision passed its local engine suite, public OEM pipeline smoke, and frontend compilation in the recorded environment. This supports a demonstration release against committed generated fixtures and selected public corpora. It does not support a claim of field validation for any real OEM DVR disk.

## Reproduction controls still required

For a formal validation package, record the source revision identifier, clean-environment dependency installation, exact OS and tool versions, test stdout/stderr, fixture hashes recomputed independently, installer hash/signature, hardware inventory, operator identity, and retained output artifacts.
