# Release checklist and external blockers

Status date: 1 September 2026. A checked item means evidence exists in this repository or the recorded command run; it does not broaden the stated scope.

## Source and build

- [x] Version aligned at 0.6.0 in engine, package, configuration, and Tauri configuration.
- [x] Complete Python suite exits successfully: 50 passed, one external-OEM test skipped.
- [x] SAC-safe local desktop path documented (`scripts/run-desktop-sac-safe.ps1`, `desktop.py --production`).
- [x] GitHub Actions builds PyInstaller sidecar + Tauri installers on `windows-latest` (no local SAC).
- [x] Root `npm run build` exits successfully.
- [x] Smoke workflow passes 42/42 against live engine.
- [x] Signed tool-verification HTML/PDF export implemented and tested.
- [x] PyInstaller frozen engine builds and reaches ready state (port binding verified on alternate port when 8787 is occupied).
- [ ] Pin `pytsk3` and `pywebview` to exact reviewed versions for a reproducible release.
- [ ] Produce MSI/NSIS installers from a clean release environment (local Windows Application Control blocked Rust DLL load during prior attempt).
- [ ] Record installer SHA-256, software signature, timestamp, and clean-machine install/uninstall results.
- [ ] FFmpeg absent locally — segment MP4 remux and analytics paths that require FFmpeg will warn or fall back to raw H.264.
- [ ] Authenticode signing not exercised — no release certificate configured in this workspace.
- [ ] Resolve or accept with rationale the Browserslist-age and mixed dynamic/static import warnings.

Evidence: `package.json`, `engine/app/__init__.py`, `engine/app/core/config.py`, `src-tauri/tauri.conf.json`, `engine/requirements.txt`, `requirements-desktop.txt`, and [Validation report](VALIDATION-REPORT.md).

## Forensic validation

- [x] Generated known-answer fixtures have recorded SHA-256 values.
- [x] Generated Dahua, Hikvision, Honeywell, and FAT16 recovery regressions pass.
- [x] Acquisition copy, checkpoint, resume, and destination integrity paths pass file-source tests.
- [ ] Obtain lawfully shareable, independently sourced disk images for every claimed OEM/storage family.
- [ ] Record device model, firmware, disk topology, deletion action, ground truth, acquisition tool, hashes, and custodian.
- [ ] Measure recall, false positives, channel accuracy, timestamp accuracy, fragmentation behavior, overwrite behavior, and full-disk performance.
- [ ] Validate hardware write blockers and Windows physical-drive acquisition with representative devices.
- [ ] Validate damaged-sector behavior, E01 input, large files, low disk space, interruption, and resume on release hardware.
- [ ] Obtain independent examiner reproduction and laboratory sign-off.

External blocker: real OEM specimens are absent from `validation_data/manifest.json`; public CFReDS and Digital Corpora references in `DEVIATIONS.md` do not supply the required vendor stores.

## Security and integrity

- [x] Bundle traversal and altered-payload rejection tests pass.
- [x] Report generation fails when custody verification fails.
- [ ] Complete an independent security review of local API exposure, parser inputs, archive handling, filesystem permissions, and update/install chain.
- [ ] Remove or formally risk-accept inline script permission in the Tauri content-security policy.
- [ ] Minimize Tauri filesystem and shell permissions after release-flow verification.
- [ ] Define key backup, rotation, revocation, compromise, and examiner attribution procedures.
- [ ] Integrate approved institutional certificates and trusted timestamps where required.
- [ ] Verify artifact/database backup, restore, retention, deletion, and access-audit procedures.

Evidence: `engine/tests/test_case_bundle_security.py`, `engine/app/services/reporting.py`, `src-tauri/tauri.conf.json`, `src-tauri/capabilities/default.json`, and `engine/app/core/signing.py`.

## Legal, privacy, and licensing

- [x] Section 63 appendix links India Code and official Act text.
- [x] Direct dependency review is documented.
- [ ] Counsel approves the case-specific certificate and transitional-law handling.
- [ ] Add an approved Pramaan project license; none was found at repository root.
- [ ] Generate and review a complete transitive dependency inventory and include required license texts.
- [ ] Document lawful authority, privacy minimization, retention, disclosure, and subject-access policy.
- [ ] Approve human custody forms and align terminology with agency procedure.

Evidence: [Section 63 appendix](BSA-SECTION-63-CERTIFICATE.md), [Third-party notices](THIRD-PARTY-NOTICES.md), and repository license-file inventory.

## Product communication

- [x] OEM capability levels distinguish experimental parsers from acquisition plus generic recovery.
- [x] Documentation expressly disclaims real-OEM field validation.
- [x] User and operations guidance include failure paths and escalation conditions.
- [ ] Ensure installer, application, demo script, submission deck, and spoken claims use the same capability levels.
- [ ] Publish release notes with known issues, supported environment, data migration, and rollback procedure.

## Release decision

**Controlled SIH demonstration:** conditionally supportable using generated specimens and explicit caveats.

**Operational forensic deployment:** blocked.

**Unqualified courtroom or real-OEM accuracy claim:** blocked.

The blockers require external specimens, independent personnel, institutional policy, legal review, signing infrastructure, or release engineering evidence not present in this repository. They cannot be closed by documentation alone.
