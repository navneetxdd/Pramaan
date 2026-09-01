# SIH26150 release audit — Pramaan 0.6.0

Audit date: 1 September 2026  
Decision scope: repository implementation and recorded local verification  
Evidence rule: generated fixtures demonstrate code paths; they do not establish performance on real recorder disks.

## Executive decision

Pramaan presents a coherent case-to-report demonstration with acquisition, integrity checks, three experimental parser families, generic recovery, custody chaining, signed reports, and signed case transfer. It is suitable for a controlled SIH demonstration when every OEM claim uses the levels below. Operational deployment and unqualified evidentiary claims remain blocked.

## Requirement assessment

| Requirement | Current evidence | Audit result |
|---|---|---|
| Standardized acquisition | read-only source open, raw DD copy, checkpoint/resume, MD5/SHA-256, destination rehash, sidecar, bad-sector map | demonstrated with file-source tests; physical media not independently validated |
| Multi-vendor identification | marker profiles for eight named OEMs | implemented as hints, not conclusive attribution |
| OEM recovery | generated-fixture paths for Dahua DHAV, Hikvision HKVI, and Honeywell layout | experimental; no real OEM disks |
| Broad fallback | filesystem undelete and H.264 carving | implemented; completeness and time/channel meaning are limited |
| Timeline | byte-offset sequencing and drift endpoint | implemented; wall-clock recovery is not generally established |
| Custody | SHA-256-chained SQLite rows and verification gate | tested; human identity and privileged-host controls remain external |
| Reporting | JSON, HTML, signed PDF | generated in tests; local self-signed identity only |
| Case transfer | signed manifest, embedded certificate, per-file SHA-256, guarded ZIP import | round trip and tamper/traversal rejection tested |
| Desktop | React/Vite in Tauri configuration | frontend compiles; installer and clean-machine evidence absent |
| Legal appendix | Section 63 official links and completion aid | documented; legal review and signatures external |

Evidence: `engine/tests/`, `engine/app/services/physical_imaging.py`, `engine/app/services/recovery.py`, `engine/app/services/reporting.py`, `engine/app/services/case_bundle.py`, `src-tauri/tauri.conf.json`, and [Validation report](VALIDATION-REPORT.md).

## OEM claim boundary

| OEM | Permitted release statement |
|---|---|
| Dahua | experimental DHAV parser verified against generated known-answer data |
| Hikvision | experimental HKVI parser verified against generated known-answer data |
| Honeywell | experimental layout/index/carve parser verified against generated known-answer data |
| CP Plus | acquisition and generic recovery; Dahua routing is an unconfirmed hypothesis |
| Uniview | acquisition and generic recovery; Hikvision routing is an unconfirmed hypothesis |
| TP-Link | acquisition and generic recovery only |
| Godrej | acquisition and generic recovery only |
| Matrix | acquisition and generic recovery only |

No OEM qualifies as a validated parser against independent real-recorder media in this release. Evidence: `validation_data/manifest.json` has an empty `oem_files` array, and the external-OEM test was skipped because no image was present.

## Verification record

Fresh commands executed in the repository:

```powershell
python -m unittest discover -s engine/tests -p "test_*.py" -v
npm run build
```

Recorded outcomes:

- engine: **50 passed, 1 skipped** (~22s); smoke workflow **42/42**; frozen sidecar builds via PyInstaller; SAC-safe pywebview desktop path;
- interface: Vite 5.4.19 transformed 1716 modules and completed in 6.32 seconds with warnings.

See [Validation report](VALIDATION-REPORT.md) for warning details and test-to-capability mapping.

## Material risks

1. Detection relies on marker occurrence and may misattribute rebadged or unrelated media.
2. Generated data is authored alongside the parser and cannot expose all independent-media assumptions.
3. Generic carving may miss fragmentation, overwritten data, encryption, proprietary packing, and RAID.
4. Offset labels are not recorder wall-clock timestamps.
5. Software read-only access does not replace a validated hardware write blocker.
6. A local self-signed certificate provides integrity evidence but not institutional identity or trusted time.
7. A privileged host user can alter application data or signing material outside Pramaan's controls.
8. Project licensing, complete transitive notices, installer signing, and clean-machine validation are incomplete.

Evidence and mitigations: [Architecture](ARCHITECTURE.md), [Capabilities and limitations](CAPABILITIES-AND-LIMITATIONS.md), and [Release checklist](RELEASE-CHECKLIST.md).

## Audit verdict

- Controlled SIH demonstration with generated specimens: **proceed with caveats**.
- Claim of full multi-vendor parser validation: **do not make**.
- Operational forensic release: **do not release yet**.
- Court submission: requires case-specific independent verification, custody records, official Section 63 certificate completion, and legal approval.

The external blockers and closure evidence are listed in [Release checklist](RELEASE-CHECKLIST.md).
