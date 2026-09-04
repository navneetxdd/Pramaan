# Pramaan Validation Report

Generated: 2026-09-01 (audit-fix pass)

## Executive summary

Pramaan is a SIH26150-oriented forensic workstation for CCTV/DVR evidence. This report records **what was verified with commands**, not aspirational claims.

| Capability | Status | Evidence |
|---|---|---|
| Dahua DHAV fixture (FFmpeg layout) | **Pass** | `ffprobe` reports `format_name=dhav`; `test_export_playable` passes in isolation |
| Dahua/Hikvision decodable H.264 in specimens | **Pass** | Whole access units (SPS+PPS+IDR); deterministic `build_dahua_lab_specimen()` SHA-256 |
| Honeywell end-to-end (recover → timeline → analytics) | **Pass** | `test_e2e_honeywell.py` |
| Hikvision HIKBTREE index → H.264 NAL extraction | **Pass (emulated image only)** | `test_hikvision_fs.py`, `test_e2e_hikvision.py`; see [Hikvision validation methodology](#hikvision-validation-methodology) |
| E01 decode for identify/structure/bytes | **Pass** | `image_io.open_evidence_readonly` + pyewf; structure probe uses decoded bytes |
| NIST nps-2009-canon2-gen6.E01 | **Pass** | pyewf + pytsk3 FAT16 undelete → **6** deleted root entries (`test_canon2_real_recovery.py`) |
| Real Dahua `.dav` (PRONOM sample) | **Fetch-on-demand** | `fetch_validation_assets.py --real-dvr`; `test_canon2_real_recovery.py::DahuaRealDavTests` when present |
| Public DVR **disk images** | **Unavailable** | No authoritative Dahua/Hikvision/Honeywell disk images on Digital Corpora or CFReDS |

## Test suite (engine)

```
python -m pytest engine/tests -q          → 110 passed, 12 skipped
python -m pytest engine/tests/test_export_playable.py -q  → pass (isolated)
python -c "… build_dahua_lab_specimen twice …" → identical SHA-256
```

## Synthetic OEM specimens

- **Dahua**: DHAV frames per `libavformat/dhav.c` (24-byte header, bitfield date, no 0x72 TLV). DHFS4.1 is a **detection marker only** — recovery is DHAV frame carving.
- **Hikvision**: Master sector @ `0x200`, HIKBTREE index, and data blocks holding **raw H.264 Annex-B NAL units behind proprietary Hikvision picture-index headers** (`00 00 01 BA` / `00 00 01 BC`). These headers are byte-identical to an MPEG-PS pack header but are **not** MPEG-PS — the payload is an elementary H.264 stream and must be treated as such (Han 2015 §2.3). No fabricated HKVI per-frame magic.
- **Honeywell**: Expired-index heuristic + NAL framing; reference path for playback/analytics.

## Hikvision validation methodology

> **Disclosure — the Hikvision filesystem engine has NOT been validated against a real
> physical drive.** Every Hikvision result in this report was produced against an **emulated
> proof-of-concept image**, not a field acquisition. This is a temporary validation setup and
> must be repeated against a genuine Hikvision drive before any of these results are presented
> as evidence of field readiness.

**What the emulated image is.** `engine/tests/support/hikvision_builder.py` constructs a disk
image whose filesystem structures follow the layout published in Han, Jeong & Lee, *Analysis of
the HIKVISION DVR File System* (ICDF2C 2015, LNICST 157, pp. 189–199), cross-checked against the
independent open-source extractor `fmpfeifer/hikextractor`, which runs against genuine drives.
Every offset used is catalogued with its source in `docs/reference/hikvision_fs.md`. Video
payload is real H.264 from the CAVIAR Walk1 reference clip (CC BY-SA), written behind genuine
Hikvision picture-index headers.

**What this does and does not establish.**

| Establishes | Does **not** establish |
|---|---|
| The parser correctly reads the *published* HIKBTREE layout | That the published layout matches the firmware on any specific seized recorder |
| Deleted-entry classification, timestamp-confidence ladder, and SPS/VUI metadata extraction are correct given that layout | That real-world index corruption, overwrite patterns, or vendor firmware variants are handled |
| Memory and performance contracts hold on a large sparse image | Behaviour on a multi-terabyte drive with thousands of populated data blocks |

**Ground truth asserted by the test suite** (`engine/tests/test_hikvision_fs.py`, 42 tests):
6 recordings across 2 channels, exactly 1 correctly classified
`deleted (index entry cleared)`, 1 in-progress `recording`, 1 unused index slot correctly
excluded, and 320x240 @ 6 fps decoded from the real H.264 SPS/VUI rather than defaulted.

**Provenance is enforced in the tooling, not just documented.** The emulated image carries a
`PRAMAAN-EMULATED-HIKVISION-FS` stamp in its first sector, and
`scripts/validation/verify_engine_output.py` refuses to label any unstamped image as a real
acquisition — it reports `UNVERIFIED - operator-supplied; confirm provenance from the custody
record`. A file path is not evidence of provenance.

**Known gap in event classification.** `event_type` reports `continuous` / `event` / `unknown`.
It is deliberately **not** reported as `motion`, because distinguishing motion from other alarm
classes requires the `RATS` system-log record field offsets, which we could not establish from a
citable public source. See `docs/reference/hikvision_fs.md` §4 and §11.

## Real-media claims (run after `--real-fs` / `--real-dvr`)

1. **Canon2 E01**: `recover_filesystem` on `nps-2009-canon2-gen6.E01` returns **6** segments tagged `filesystem_deleted_inode` (DCIM, $FAT*, volume label). Use **`generic_tier2`** adapter in the Recover UI.
2. **Real Dahua `.dav`**: When fetched, `DahuaRealDavTests` validates ≥10 segments and slice/IDR NALs in the first unwrapped chunk.

## AI analytics

- Pipelines: MOG2, frame-diff, YuNet/Haar faces, YOLOX-nano objects.
- CAVIAR Walk1 (CC BY-SA) is the committed analytics reference; MEVA (CC-BY-4.0) optional via fetch script.
- Findings are **investigative leads only** — excluded from signed report unless examiner marks INCLUDED.

## Known limitations

- No field DVR disk validation; synthetic + PRONOM/FFmpeg samples only for OEM parsers. The
  Hikvision filesystem engine specifically is validated against an **emulated** image built from
  published research — see [Hikvision validation methodology](#hikvision-validation-methodology).
- Logical network pull uses **HTTP Digest** (Hikvision ISAPI / Dahua CGI). Clips only — no deleted-data recovery. Enable with `PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1`.
- SQLite global write lock serialises heavy jobs (acceptable for demo, not multi-examiner production).

## Non-deterministic fixture fix

Prior builds used a module-global NAL cursor — `test_export_playable` passed only in full suite order. Fixed with `NalPayloadSource.reset()` + `conftest.py` autouse reset.
