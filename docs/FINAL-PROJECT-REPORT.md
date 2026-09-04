# Pramaan Final Project Report

## Architecture

Tauri + React UI; FastAPI engine; SQLite custody; OEM parsers + pytsk3/libewf tier-2; PAdES reports.

## OEM analysis

| Vendor | Approach | Validation |
|---|---|---|
| Dahua | DHAV frame carver (not full DHFS FS) | Synthetic + optional real `.dav` |
| Hikvision | HIKBTREE index → raw H.264 NAL units behind proprietary picture-index headers | **Emulated image only** — see methodology note below |
| Honeywell | Index/NAL carve | End-to-end demo path |
| Generic | pytsk3 on E01/DD | NIST canon2 E01 |

No public DVR disk images for any OEM — only frame/container samples and NIST camera-card E01.

### Hikvision: stream format

Hikvision data blocks store **raw H.264 Annex-B NAL units**, each preceded by a proprietary
Hikvision **picture-index header** (`00 00 01 BA` or `00 00 01 BC`). That header is byte-identical
to an MPEG-PS pack header but the payload is **not** a program stream — it is an elementary H.264
stream, and treating it as MPEG-PS yields output no demuxer can read. This is also why Hikvision
footage renders with artefacts in third-party players (Han 2015 §2.3). Resolution and frame rate
are therefore decoded from the H.264 SPS/VUI, not from any container header. Full offset
catalogue with sources: `docs/reference/hikvision_fs.md`.

### Hikvision: validation provenance

> **The Hikvision filesystem engine has NOT been validated against a real physical drive.**

Validation was performed against an **emulated proof-of-concept image** whose structures follow
the layout published in Han, Jeong & Lee, *Analysis of the HIKVISION DVR File System* (ICDF2C
2015), cross-checked against the independent extractor `fmpfeifer/hikextractor`. Video payload is
real H.264 (CAVIAR Walk1, CC BY-SA).

This is a **temporary validation setup**, adopted because no authoritative Hikvision disk image
is publicly available and no physical drive has yet been acquired. It demonstrates that the
parser correctly implements the published filesystem specification. It does **not** demonstrate
correctness against any specific seized recorder, firmware variant, or real-world overwrite
pattern. These results must be re-run against a genuine Hikvision drive before being presented
as evidence of field readiness.

The emulated image is stamped `PRAMAAN-EMULATED-HIKVISION-FS` in its first sector, and the
verification tooling refuses to label an unstamped image as a real acquisition. See
`docs/VALIDATION-REPORT.md` § Hikvision validation methodology for what the emulated validation
does and does not establish.

## Limitations

- SQLite global write lock
- Logical pull: Digest auth; RTSP fallback on firmware quirks
- AI: investigative leads only
- UI: incremental Visily instrumentation theme

See `docs/VALIDATION-REPORT.md` for command-verified results.
