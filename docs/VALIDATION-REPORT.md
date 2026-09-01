# Pramaan Validation Report

Generated: 2026-09-01 (audit-fix pass)

## Executive summary

Pramaan is a SIH26150-oriented forensic workstation for CCTV/DVR evidence. This report records **what was verified with commands**, not aspirational claims.

| Capability | Status | Evidence |
|---|---|---|
| Dahua DHAV fixture (FFmpeg layout) | **Pass** | `ffprobe` reports `format_name=dhav`; `test_export_playable` passes in isolation |
| Dahua/Hikvision decodable H.264 in specimens | **Pass** | Whole access units (SPS+PPS+IDR); deterministic `build_dahua_lab_specimen()` SHA-256 |
| Honeywell end-to-end (recover → timeline → analytics) | **Pass** | `test_e2e_honeywell.py` |
| Hikvision HIKBTREE + MPEG-PS model | **Pass** | `test_e2e_hikvision.py`, `hikbtree_indexed` validation |
| E01 decode for identify/structure/bytes | **Pass** | `image_io.open_evidence_readonly` + pyewf; structure probe uses decoded bytes |
| NIST nps-2009-canon2-gen6.E01 | **Present** | sha256 `10483722d84e…`; run `fetch_validation_assets.py --real-fs` |
| Real Dahua `.dav` (PRONOM sample) | **Fetch-on-demand** | `fetch_validation_assets.py --real-dvr` when wired |
| Public DVR **disk images** | **Unavailable** | No authoritative Dahua/Hikvision/Honeywell disk images on Digital Corpora or CFReDS |

## Test suite (engine)

```
python -m pytest engine/tests -q          → 57 passed
python -m pytest engine/tests/test_export_playable.py -q  → pass (isolated)
python -c "… build_dahua_lab_specimen twice …" → identical SHA-256
```

## Synthetic OEM specimens

- **Dahua**: DHAV frames per `libavformat/dhav.c` (24-byte header, bitfield date, no 0x72 TLV). DHFS4.1 is a **detection marker only** — recovery is DHAV frame carving.
- **Hikvision**: Master block @ `0x200`, HIKBTREE index, MPEG-PS data blocks (no fabricated HKVI per-frame magic).
- **Honeywell**: Expired-index heuristic + NAL framing; reference path for playback/analytics.

## Real-media claims (run after `--real-fs` / `--real-dvr`)

1. **Canon2 E01**: Acquire → identify shows filesystem hints → recover with **`generic_tier2`** adapter → JPEG SOI or filesystem validation tags. Record exact count in this section after `test_canon2_real_recovery.py` run.
2. **Real Dahua `.dav`**: When fetched, `test_dahua_real_dav.py` validates ≥50 segments and ffprobe ≥10 frames on unwrapped H.264.

## AI analytics

- Pipelines: MOG2, frame-diff, YuNet/Haar faces, YOLOX-nano objects.
- CAVIAR Walk1 (CC BY-SA) is the committed analytics reference; MEVA (CC-BY-4.0) optional via fetch script.
- Findings are **investigative leads only** — excluded from signed report unless examiner marks INCLUDED.

## Known limitations

- No field DVR disk validation; synthetic + PRONOM/FFmpeg samples only for OEM parsers.
- Logical network pull tested against simulators; production Hikvision ISAPI / Dahua CGI require HTTP Digest.
- SQLite global write lock serialises heavy jobs (acceptable for demo, not multi-examiner production).

## Non-deterministic fixture fix

Prior builds used a module-global NAL cursor — `test_export_playable` passed only in full suite order. Fixed with `NalPayloadSource.reset()` + `conftest.py` autouse reset.
