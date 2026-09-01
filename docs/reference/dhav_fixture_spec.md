# DHAV fixture specification (FFmpeg `libavformat/dhav.c`)

Synthetic Dahua specimens and tier-1 fixtures must match this layout. Source of truth: FFmpeg `read_chunk` / `parse_ext` / `get_timeinfo`.

## Frame layout

| Offset | Size | Field |
|--------|------|-------|
| 0 | 4 | Magic `DHAV` |
| 4 | 1 | Type (`0xFD` video, `0xFC` audio) |
| 5 | 1 | Subtype |
| 6 | 1 | Channel |
| 7 | 1 | Frame subnumber |
| 8 | 4 | Frame number (u32 LE) |
| 12 | 4 | Frame length (u32 LE) — total frame including header/footer |
| 16 | 4 | Date (bitfield, LE) |
| 20 | 2 | Timestamp (u16 LE) |
| 22 | 1 | Extension length |
| 23 | 1 | Header checksum |
| 24 | N | Extension TLV (`ext_length` bytes) |
| 24+N | … | Payload (H.264 access unit) |
| end-8 | 4 | Footer magic `dhav` |
| end-4 | 4 | `seek_back` u32 LE — must equal `frame_length - 8` |

## Rules

- Header is **24 bytes**, not 32.
- Do **not** invent `0x72` TLV types; use FFmpeg extension parsing only.
- Payload must be a **complete decodable H.264 access unit** (SPS + PPS + IDR/slice), not a truncated NAL.
- Lab specimens must be deterministic (`NalPayloadSource.reset()` before each build).

## Verification

```powershell
python -m pytest engine/tests/test_export_playable.py -q
ffprobe -f dhav -i validation_data/fixtures/tier1/dahua_known_answer.bin
```
