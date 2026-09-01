# Acquisition, recovery, custody, and transfer procedures

These procedures are operational guidance. Agency policy, warrant scope, laboratory quality controls, and court directions take precedence.

## A. Acquisition

### Before connection

1. Confirm legal authority, case identifier, examiner identity, date/time, recorder state, and scope.
2. Photograph the recorder, ports, cabling, display, serial/model labels, storage arrangement, and visible clock.
3. Record timezone, displayed time, reference time, and observed drift before power-state changes.
4. Decide whether live collection or shutdown is justified; record the decision and rationale.
5. Prepare destination storage with sufficient free space. Record workstation and Pramaan versions.
6. Use an independently validated hardware write blocker when the source can be detached. Record make, model, serial, firmware, and verification result.

### Imaging

1. Create the case and enter an examiner name.
2. Select the physical source or an existing forensic image. On Windows, raw physical-device access requires elevation.
3. Confirm source and destination identifiers before starting.
4. Start imaging. Do not disconnect the source while the job is active.
5. If interrupted, preserve the partial destination and resume only against the same source after rechecking identifiers.
6. At completion, record byte count, MD5, SHA-256, verification status, and bad-sector count. Preserve the `.sha256` sidecar.
7. If unreadable sectors exist, record that Pramaan zero-filled those sectors and attach the bad-sector map.

Stop if the source identity is uncertain, the destination points to evidence media, hashes mismatch, or unexplained read errors occur.

Evidence: `engine/app/services/physical_imaging.py`, `engine/app/services/disk_enumeration.py`, `engine/tests/test_m4_acquisition.py`, and `engine/app/api/v1/version.py`.

## B. Recovery and examination

1. Verify the stored image hash before recovery.
2. Review identification markers and selected adapter. Treat CP Plus→Dahua and Uniview→Hikvision routes as unconfirmed lineage hypotheses.
3. Check the capability level in [OEM capabilities](CAPABILITIES-AND-LIMITATIONS.md).
4. Run recovery on the forensic copy, not original media.
5. Preserve job status, adapter, parser validation label, offsets, channel, and frame count.
6. Review every exported sequence for decodability, continuity, duplicate content, channel attribution, and timestamp meaning.
7. Corroborate material findings with recorder configuration, scene content, another forensic method, and case facts.
8. Document negative findings narrowly: state what adapter, byte range, and method were used; do not state that footage never existed.
9. Apply drift correction only from a documented recorder/reference-time observation.

Stop and escalate when encryption, RAID, proprietary fragmentation, unsupported storage, implausible timestamps, or substantial false positives are observed.

Evidence: `engine/app/services/recovery.py`, `engine/app/parsers/manufacturer_detect.py`, `engine/app/parsers/generic_tier2.py`, and `engine/app/parsers/temporal_sequencing.py`.

## C. Custody

For each receipt, imaging session, verification, recovery, export, handover, return, or disposal:

1. Record UTC time and local time, actor, action, item identifier, source/destination, purpose, and authorizing reference.
2. Record seal condition before and after access.
3. Record evidence and working-copy hashes.
4. Keep original media sealed except for authorized acquisition.
5. Store evidence, signing material, and backups under separate access controls.
6. Verify the Pramaan custody chain before report generation and after case import.
7. Export the machine ledger together with signed human custody forms; neither replaces the other.

Pramaan chains custody rows with SHA-256 and refuses report generation when chain verification fails. This detects certain database changes; it does not authenticate a person or protect against deletion by a privileged host operator.

Evidence: `engine/app/core/db.py`, `engine/app/core/repository.py`, `engine/app/services/reporting.py`, and `engine/tests/test_v1_cases.py`.

## D. Case transfer

### Sender

1. Verify evidence hashes and custody chain.
2. Export a `.pramaan.zip` bundle.
3. Record bundle filename, byte size, SHA-256 calculated by an independent approved tool, signer fingerprint, sender, recipient, channel, and time.
4. Transfer the bundle and the recorded SHA-256 through separate authenticated channels where feasible.
5. Retain the source bundle unchanged until receipt is confirmed.

### Recipient

1. Confirm sender identity and expected bundle SHA-256 before import.
2. Import into a controlled workstation. Pramaan verifies manifest signature, embedded certificate fingerprint, safe archive paths, and each declared file hash.
3. Compare the displayed signer fingerprint with the sender's separately communicated value.
4. Reverify imported evidence hashes and custody chain.
5. Record acceptance, discrepancies, and any rejected import.

The embedded self-signed certificate establishes consistency with the bundle's signing key; it does not by itself establish the sender's legal identity.

Evidence: `engine/app/services/case_bundle.py`, `engine/app/core/signing.py`, `engine/app/api/v1/case_transfer.py`, `engine/tests/test_m5_case_transfer.py`, and `engine/tests/test_case_bundle_security.py`.
