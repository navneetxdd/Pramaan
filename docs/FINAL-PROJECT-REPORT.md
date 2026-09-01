# Pramaan Final Project Report

## Architecture

Tauri + React UI; FastAPI engine; SQLite custody; OEM parsers + pytsk3/libewf tier-2; PAdES reports.

## OEM analysis

| Vendor | Approach | Validation |
|---|---|---|
| Dahua | DHAV frame carver (not full DHFS FS) | Synthetic + optional real `.dav` |
| Hikvision | HIKBTREE → MPEG-PS | hikextractor-aligned fixture |
| Honeywell | Index/NAL carve | End-to-end demo path |
| Generic | pytsk3 on E01/DD | NIST canon2 E01 |

No public DVR disk images for any OEM — only frame/container samples and NIST camera-card E01.

## Limitations

- SQLite global write lock
- Logical pull: Digest auth; RTSP fallback on firmware quirks
- AI: investigative leads only
- UI: incremental Visily instrumentation theme

See `docs/VALIDATION-REPORT.md` for command-verified results.
