# Pramaan SIH26150 final project report

## Executive summary

Pramaan 0.6.0 is a local desktop forensic workstation for DVR/NVR acquisition, storage-family identification, recovery candidate extraction, timeline review, integrity verification, custody logging, reporting, and signed case transfer. The implementation demonstrates an end-to-end workflow with generated known-answer specimens. It has not been validated against independent real OEM disks and must not be presented as field-validated.

## Problem and design response

DVR/NVR evidence varies by storage family, recorder firmware, filesystem, video container, clock behavior, and deletion mechanism. Pramaan addresses workflow fragmentation with a single case model and adapter registry:

- raw DD acquisition with checkpoints, resume, bad-sector recording, MD5/SHA-256, and destination rehash;
- marker-based manufacturer hints and adapter routing;
- dedicated generated-fixture parser paths for DHAV, HKVI, and a Honeywell layout;
- filesystem undelete or generic H.264 carving when no dedicated parser evidence exists;
- offset-based sequencing with optional drift correction;
- hash-chained custody, reports, local PAdES signing, and signed bundle transfer.

Evidence: `engine/app/services/physical_imaging.py`, `engine/app/parsers/registry.py`, `engine/app/parsers/manufacturer_detect.py`, `engine/app/services/recovery.py`, `engine/app/services/reporting.py`, and `engine/app/services/case_bundle.py`.

## Implementation

The React/Vite interface runs in a Tauri 2 desktop shell. A loopback FastAPI engine owns forensic operations and SQLite metadata. The default workspace is `~/ForensicWorkstation/data`, with per-case evidence and separate report, bundle, and signing directories. Architecture details and trust assumptions are recorded in [Architecture](ARCHITECTURE.md).

The database stores cases, devices, acquisition checkpoints, recovered sequences, custody events, analytics findings, reports, verification runs, and background jobs. Custody rows chain the previous and current row hashes with SHA-256.

Evidence: `src-tauri/tauri.conf.json`, `engine/app/core/config.py`, and `engine/app/core/db.py`.

## Capability outcome

Three parser families pass generated known-answer tests:

- Dahua DHAV signatures and frame consistency;
- Hikvision HKVI block checks;
- Honeywell generated partition/layout, index, and raw-video-region paths.

CP Plus and Uniview routing remains an unvalidated lineage hypothesis. TP-Link, Godrej, and Matrix have acquisition plus generic recovery only. No real OEM image appears in the validation manifest. See [Capabilities and limitations](CAPABILITIES-AND-LIMITATIONS.md).

## Verification outcome

On 1 September 2026, the integrated Python suite recorded **48 passed, 1 skipped** (external OEM drop zone empty). Smoke workflow **42/42**. Root production frontend build completed successfully. PyInstaller frozen engine reaches ready state independently of a system Python install. Exact commands, environment, warning details, and scope are in [Validation report](VALIDATION-REPORT.md).

This evidence supports source-level demonstration against committed generated fixtures. It does not measure real-media accuracy, completeness, false positives, performance at full-disk scale, or legal admissibility.

## Evidence integrity and transfer

Acquisition records SHA-256 and MD5 and rehashes the destination. Report generation verifies the custody chain and signs PDF output using a persisted local RSA certificate. Case bundles include an embedded certificate, RSA-PSS manifest signature, and per-file SHA-256 values. Import rejects unsafe archive paths, unsupported structure, signature failure, missing content, and hash mismatch.

The certificate is self-signed. It provides integrity evidence tied to its fingerprint but no institutional identity or trusted timestamp. Human custody documentation and independent hashes remain required.

Evidence: `engine/app/services/physical_imaging.py`, `engine/app/core/signing.py`, `engine/app/services/reporting.py`, `engine/app/services/case_bundle.py`, and `engine/tests/test_case_bundle_security.py`.

## Legal and operational readiness

The [operations procedures](OPERATIONS-SOP.md) define acquisition, recovery, custody, and transfer controls. The [Section 63 appendix](BSA-SECTION-63-CERTIFICATE.md) links the official statute and provides a case-fact worksheet. Legal review and case-specific signatures remain outside the software.

## Release assessment

Pramaan is suitable for a controlled SIH demonstration and further laboratory validation. It is not ready for an unqualified production or courtroom claim. Release is blocked externally by OEM specimen access, independent validation, project licensing, full dependency notices, installer signing, clean-machine testing, hardware write-blocker evidence, security review, and institutional certificate/time infrastructure.

The authoritative release decision record is [Release checklist](RELEASE-CHECKLIST.md).
