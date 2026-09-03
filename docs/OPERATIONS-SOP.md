# Pramaan Operations SOP

**Scope:** Examiner workflow for the Pramaan desktop workstation.  
**Assumption:** Write-blocker or forensic duplicate for physical media; operator drop folder for corpora.

## 1. Case creation

1. Create case with examiner name (custody actor for all subsequent actions).
2. Set classification / distribution on report when exporting (free-text, per case).

## 2. Acquisition (Step 1)

| Method | When to use | Integrity |
|---|---|---|
| DD imaging | USB/SD/SATA via write-blocker | Streaming SHA-256 + MD5; checkpoint/resume |
| Upload | Existing E01/DD/IMG | Re-hash on ingest; mismatch → quarantine |
| OEM drop folder | `validation_data/oem/` or `PRAMAAN_OEM_IMAGE_DIR` | Same hash pipeline |
| Logical pull | Live NVR (Digest auth) | Clips only — no unallocated recovery |
| Synthetic specimen | Lab/demo | Labelled known-answer; not field evidence |

**Rule:** On hash mismatch, do not proceed — re-acquire or document exception in custody log.

## 3. Identification (Step 2)

- Automatic marker scan + filesystem hints.
- **Dahua** → `dahua_dhav` (DHAV frame carver; DHFS string is routing hint only).
- **Hikvision** → `hikvision` (HIKBTREE index → H.264 NAL extraction; data blocks hold raw
  H.264 Annex-B behind proprietary picture-index headers, not MPEG-PS).
- **Inconclusive** → `needs_selection`; pick adapter manually on Recovery.
- **FAT32/NTFS/E01 camera cards** → prefer `generic_tier2`.

## 4. Recovery (Step 3)

1. Select evidence image and recovery adapter (defaults to identification recommendation).
2. Run recovery; review confidence tiers and validation labels.
3. Superseded runs are custody-logged.

## 5. Timeline & playback (Step 4)

- Time mode when recorder timestamps recovered; otherwise byte-offset order (labelled).
- Shared transport controls all lanes — no per-lane scrubbers.

## 6. AI analytics (optional)

- Run after recovery; review `demo_mode_unavailable` if export lacks decodable frames.
- Mark findings INCLUDED/EXCLUDED before report (leads ≠ evidence).

## 7. Custody & report (Steps 5–6)

- Append-only SHA-256 linked custody log; report **409** if chain broken.
- Export: JSON, HTML preview, PAdES PDF, `.pramaan.zip`.
- Custody tip hash may appear in report header as integrity reference.

## 8. Validation datasets

```bash
python scripts/validation/fetch_validation_assets.py --real-fs
python scripts/validation/fetch_validation_assets.py --real-dvr
python scripts/validation/build_oem_disk_fixtures.py
```

Settings → Validation datasets or manifest at `validation_data/manifest.json`.
