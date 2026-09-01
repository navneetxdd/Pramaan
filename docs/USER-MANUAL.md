# Pramaan User Manual

## Navigation

Sidebar steps unlock after case creation and acquisition:

1. **Acquire** — image, upload, OEM drop, logical pull, synthetic specimens  
2. **Identify** — vendor hits, filesystem tree, hex preview  
3. **Recover** — adapter selector, engine log, confidence donut, segment table  
4. **Timeline** — multi-track ruler, playback deck, shared transport  
5. **AI Analytics** — motion/face/object pipelines  
6. **Custody** — hash-chained audit log  
7. **Report** — live HTML preview, JSON/PDF/signed exports  

## Acquire screen

- Enter examiner name (required for custody).
- Left column scrolls at 720p — OEM drop and logical pull sections remain reachable.
- **Network logical pull** (requires `PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1`): HTTP Digest auth to Hikvision ISAPI or Dahua CGI. Choose HTTP/HTTPS scheme. Exports accessible clips only — not a substitute for disk imaging.

## Recovery screen

- **Recovery adapter** dropdown: `dahua_dhav`, `hikvision`, `honeywell`, `h264_carve`, `generic_tier2`.
- Use **`generic_tier2`** for NIST camera-card E01 images.
- Confidence donut centre shows total segment count (0 when empty).

## Timeline & playback

- Byte-offset ticks use integer hex (no fractional labels).
- Play/pause on shared transport; lane videos have no separate controls.

## Report

- Live HTML preview of the signed forensic report.
- Chain must be INTACT before signed PDF export.

## Settings

- Working directory: set `FORENSIC_WORKSTATION_DATA` before launch (read-only in UI).
- **Validation datasets**: fetch Digital Corpora E01, PRONOM `.dav`, and other manifest entries.
- Parser sanity check runs tier-1 fixture verification and optional real-media stages.
