# OEM capabilities and honest limitations

## Capability levels

- **Validated parser** — dedicated parser passes committed known-answer fixtures and end-to-end automated tests.
- **Experimental parser** — dedicated format logic passes generated fixtures, but no independent real-recorder disk image is present.
- **Acquisition + generic only** — media can be imaged and routed to filesystem recovery or generic H.264 carving; there is no brand-specific parser evidence.

These levels describe repository evidence, not courtroom admissibility. `validation_data/manifest.json` records no OEM files, and the external-media test was skipped on 1 September 2026 because the drop zone was empty.

## OEM matrix

| Declared OEM | Release level | Implemented route | Evidence and caveat |
|---|---|---|---|
| Dahua | Experimental parser | `dahua_dhav` | Four-check DHAV generated fixture and adapter tests pass; no real Dahua disk image |
| Hikvision | Experimental parser | `hikvision` | Four-check HKVI generated fixture and end-to-end test pass; no HIKBTREE implementation or real disk image |
| Honeywell | Experimental parser | `honeywell` | Generated GPT/layout, expiration-index, and format-carve paths pass; no real Honeywell disk image |
| CP Plus | Acquisition + generic only | marker currently routes to `dahua_dhav` | routing is a lineage hypothesis; there is no CP Plus fixture or real-media result |
| Uniview | Acquisition + generic only | marker currently routes to `hikvision` | routing is a lineage hypothesis; there is no Uniview fixture or real-media result |
| TP-Link | Acquisition + generic only | `generic_tier2` | token detection plus filesystem/H.264 path only |
| Godrej | Acquisition + generic only | `generic_tier2` | token detection plus filesystem/H.264 path only |
| Matrix | Acquisition + generic only | `generic_tier2` | token detection plus filesystem/H.264 path only |

Evidence: `engine/app/parsers/registry.py`, `engine/app/parsers/manufacturer_detect.py`, `engine/app/parsers/dahua_dhfs.py`, `engine/app/parsers/hikvision.py`, `engine/app/parsers/honeywell.py`, `engine/tests/test_m2_parsers.py`, `engine/tests/test_m3_parsers.py`, `engine/tests/test_e2e_hikvision.py`, `engine/tests/test_e2e_honeywell.py`, and `validation_data/manifest.json`.

## Limitations matrix

| Area | Current behavior | Consequence | Required examiner action |
|---|---|---|---|
| OEM field validation | no real OEM media recorded | sensitivity, specificity, timestamp accuracy, and false-positive rates are unknown | validate against independently sourced write-blocked images |
| Vendor detection | byte-token scoring in first 64 MiB | rebadges and coincidental strings can misroute | compare partition structures, recorder model, and a second tool |
| Deleted recovery | signature/index candidates | candidate presence does not prove complete recovery | review footage continuity and surrounding metadata |
| Time | offset labels and optional drift correction | wall-clock timestamps may be absent or wrong | document recorder clock, timezone, drift, and DST |
| Dahua/Hikvision timestamps | DHAV extension TLV `0x72` and HKVI block epoch parsed from **generated fixtures only** | not verified against real recorder media | treat fixture timestamps as lab exercises; validate independently on real disks |
| Channels | parser-derived or inferred values | channel attribution may be incomplete | visually correlate cameras and recorder configuration |
| Generic carving | filesystem undelete or H.264 start-code carving | fragmented, overwritten, encrypted, or proprietary streams may be missed | report the search method and negative-result limits |
| Acquisition | raw DD output; E01 input optional | no E01 output and no compression | preserve raw image, sidecar, and storage capacity |
| Write protection | source opened read-only in software | cannot prove source media was electrically protected | use and record a validated hardware write blocker |
| Bad sectors | failed sectors are zero-filled and logged | output is not bit-identical at unreadable sectors | retain map and state the substitution |
| Encryption | no detection or decryption | encrypted footage may appear unrecoverable | escalate to vendor/legal key-recovery process |
| RAID/chip-off | unsupported | multi-disk and damaged-device cases are incomplete | use specialist acquisition tooling |
| Signatures | local self-signed certificate | integrity check lacks institutional identity and trusted timestamp | use organizational PKI and trusted time where required |
| Host security | local files and SQLite | privileged host access can alter evidence or keys | use controlled workstation, access logs, backups, and independent hashes |
| Analytics | optional scene/face processing | findings are investigative aids and may be wrong | human-review every finding; do not use as sole identification evidence |
| Legal certificate | software can supply technical facts only | an incomplete or inaccurate certificate can affect admissibility | responsible person and expert must review and sign case-specific facts |

Evidence: `engine/app/api/v1/version.py`, `engine/app/services/physical_imaging.py`, `engine/app/services/recovery.py`, `engine/app/core/signing.py`, `engine/app/services/ai_analytics.py`, and the official [Bharatiya Sakshya Adhiniyam, 2023](https://www.indiacode.nic.in/handle/123456789/20063).
