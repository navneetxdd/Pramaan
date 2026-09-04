# Handoff — Hikvision export & playback

**From:** Aravind R (3. Recovery — Hikvision engine)
**To:** Roshan (4. Timeline & Playback — export pipeline, `playable_frame_count`)
**Status of the producing side:** complete and on `aravind/hikvision-fs-engine`. The parser
emits a validated entry list; nothing below requires further engine work from me.

Files in scope are **yours** — I have not edited them:
`engine/app/api/v1/devices.py` (`export_sequence`), `engine/app/parsers/unwrap.py`,
`engine/app/services/recovery.py` (`_write_bounded_artifact`).

Background for every offset and claim here: `docs/reference/hikvision_fs.md`.

---

## 1. The H.264 payload reality — the export path is currently wrong for Hikvision

### 1.1 What is actually in the artifact

`_write_bounded_artifact` copies the parser's byte range verbatim. For Hikvision that range is
**raw H.264 Annex-B NAL units, each preceded by an 8-byte proprietary picture-index header**
([HAN2015] §2.3, and `hikvision_fs.md` §5.1):

```
00 00 01 BA   <4-byte picture index>   00 00 00 01  <NAL>   00 00 01 BA  <4-byte index>  00 00 00 01 <NAL> ...
└── marker ──┘└──── index ───────────┘ └────── real H.264 ──────────┘
```

The marker is `00 00 01 BA` or `00 00 01 BC`, followed by **4 bytes** of picture index — 8 bytes
total per NAL unit.

**`00 00 01 BA` is byte-identical to an MPEG-PS pack header but this is not MPEG-PS.** There is no
program stream, no PES layer, no pack. It is an elementary H.264 stream with a vendor prefix in
front of each NAL. This is exactly why Hikvision footage shows artefacts in any player other than
their own `player.exe`. Do not reach for a PS demuxer; there is nothing to demux.

### 1.2 The defect, measured

`unwrap_to_h264()` (`unwrap.py:26`) ends in a generic branch: find the first NAL start code, slice
from there. For a Hikvision artifact that strips **only the first** header. Measured on a real
artifact from the emulated image:

```
artifact bytes                    : 120,978
picture-index headers in artifact : 24
--- after unwrap_to_h264() ---
picture-index headers REMAINING   : 23
bytes stripped                    : 8
```

23 of 24 headers survive, embedded mid-stream. FFmpeg will resynchronise past them, but each one
corrupts the NAL boundary it sits in front of, so you get decode errors and dropped pictures — and
`playable_frame_count` will silently under-report.

### 1.3 Required change

Add a Hikvision branch to `unwrap_to_h264()`, **before** the generic NAL-start fallback. Reference
implementation, validated against all 7 recordings in the emulated image (24 → 0 markers each,
stream starts on a NAL start code, SPS survives and still decodes to 320x240 @ 6.0 fps):

```python
from engine.app.parsers.schemas.hikvision_fs import PICTURE_INDEX_BA, PICTURE_INDEX_BC

PICTURE_INDEX_LEN = 4  # 4-byte index follows the 4-byte marker

def strip_hikvision_picture_index(blob: bytes) -> bytes:
    """Remove every 00 00 01 BA|BC + 4-byte picture index, keeping the H.264 NALs."""
    out = bytearray()
    cursor = 0
    while cursor < len(blob):
        ba = blob.find(PICTURE_INDEX_BA, cursor)
        bc = blob.find(PICTURE_INDEX_BC, cursor)
        hits = [h for h in (ba, bc) if h >= 0]
        if not hits:
            out += blob[cursor:]
            break
        hit = min(hits)
        out += blob[cursor:hit]
        cursor = hit + len(PICTURE_INDEX_BA) + PICTURE_INDEX_LEN
    return bytes(out)
```

**Dispatch, not sniffing.** Do not detect Hikvision by scanning for `BA` — an arbitrary H.264
payload can contain that sequence, and stripping 8 bytes from a false positive corrupts the stream.
Dispatch on the row's `parser_name == "hikvision"`, which `list_sequences()` already returns and
`export_sequence` already has in `seq`. Pass it into the unwrap call rather than guessing inside it.

Constants are exported from `engine/app/parsers/schemas/hikvision_fs.py`; import them rather than
re-declaring the byte strings, so a future correction propagates.

### 1.4 FFmpeg invocation

Once stripped, the stream is plain Annex-B H.264. Feed it as `-f h264` (the code already does).
The reference extractor `fmpfeifer/hikextractor` remuxes real drives with:

```
ffmpeg -err_detect ignore_err -i - -c:v copy -bsf:v filter_units=pass_types=1-5
```

`filter_units=pass_types=1-5` drops non-VCL NAL types that some Hikvision firmware interleaves.
Worth adopting if you see decode noise after stripping.

### 1.5 Two things to check while you are in there

- **`export_sequence` does `artifact_path.read_bytes()`** (`devices.py`, ~line 426). A Hikvision
  data block can be 1 GB (`hikvision_fs.md` §3), so a single export can allocate a gigabyte on the
  desktop client. The engine side is now bounded end-to-end; this is the remaining place that is
  not. Stream it, or cap it.
- **`ensure_playable_h264()`** prepends SPS/PPS from the **CAVIAR fixture** when the blob lacks
  parameter sets. On a real Hikvision export that would splice a lab clip's parameter sets into
  evidence. Hikvision writes SPS per GOP so it should never fire — but if it ever does, the exported
  file is no longer a faithful copy of the evidence. Consider failing loudly instead for
  `parser_name == "hikvision"`.

---

## 2. Wiring `playable_frame_count`

### 2.1 It is already wired — it just never runs

`devices.py:523` already calls `_count_decoded_frames(mp4_path)` →
`update_sequence_playable_frame_count(segment_id, frame_count)`. `_count_decoded_frames` shells
`ffprobe -count_frames -select_streams v:0 -show_entries stream=nb_read_frames`, which is the right
command. The column is empty on every row in every case for three separate reasons:

1. **FFmpeg/ffprobe are not installed on this workstation.** `shutil.which(FFMPEG_BIN)` returns
   `None`, `transcode_to_mp4()` returns `False`, and the update block is skipped entirely.
2. **It only runs on an explicit, non-ranged export.** Guarded by `if not ranged`. Nothing populates
   the count during recovery, so the Recovery table shows `—` until an examiner exports each segment
   by hand, one at a time.
3. **Until §1.3 lands, the count would be wrong anyway** — the embedded picture-index headers cause
   decode errors, so `nb_read_frames` under-reports.

### 2.2 Recommended order

1. Install FFmpeg and put it on `PATH` (or set `FORENSIC_FFMPEG`). Nothing here is verifiable
   without it, and the app banners its absence on every page.
2. Land the §1.3 strip first. Measuring frames before that just records the corruption.
3. Then decide where the count is produced. Per-segment manual export does not scale to a
   multi-channel image; either fold it into the recovery job as a bounded post-pass, or trigger it
   lazily when the Recovery table first renders a row with a null count.
4. Keep `container_units` and `playable_frame_count` distinct. `container_units` for Hikvision is
   now `0` by design — my adapter no longer reports picture-index headers as frames, because they
   are one per NAL, not one per picture. `playable_frame_count` from ffprobe is the only real frame
   number.

### 2.3 Acceptance

For each recovered Hikvision recording, `ffmpeg -v error -i <export> -f null -` must exit 0 with no
decode errors, and `ffprobe -count_frames` must return a non-zero count consistent with
`duration × fps` from the Metadata tab (the emulated image is 6.0 fps).

---

## 3. Heads-up: a new `idr_table_scan` rung at 0.3 confidence

As of `4ce228e` the Hikvision engine emits a segment class your UI has not seen before.

[HAN2015] documents **two** ways footage stops being indexed, and they leave different evidence:

| Mode | Index flag | Index timestamps | `timestamp_source` | `timestamp_confidence` |
|---|---|---|---|---|
| §3.2 initialization | cleared | **survive** | `hikbtree_residual` | `0.5` |
| §3.3 overwriting | cleared | **wiped to `0x7FFFFFFF`** | `idr_table_scan` | **`0.3`** |

Both report `allocation_state = "deleted (index entry cleared)"` and
`validation = "hikbtree_deleted_entry"`.

**What this means for playback.** A `0.3` segment's start/end times were recovered from the IDR
table *inside the data block*, not from the index. Its own `timestamp_confidence_basis` says why:

> *index timestamps reset to sentinel; times recovered from the data block's IDR table and may
> belong to either the original or an overwriting recording*

So on a shared absolute time axis, a `0.3` lane position is materially weaker than a `0.9` one and
should be visually distinguishable — the segment is real and playable, but *when* it happened is
provisional. I would not let it silently anchor a cross-channel alignment.

**On a real seized drive this is the common case**, not the exotic one: a recorder that has been
running for months has wrapped, so overwriting dominates and initialization is rare.

**Also new for you:** `allocation_state = "recording"` — an in-progress recording (allocated flag,
sentinel start). Previously these were silently dropped. It has no end time from the index, so it
also resolves via `idr_table_scan`.

### 3.1 One line you need in `timeline.py`

`timeline.py:30` builds `deleted_candidate` from a hardcoded validation set that does not include
mine, so Hikvision deleted recordings currently do **not** register as deleted on your timeline:

```python
            "deleted_candidate": seq["validation_level"] in {
                "honeywell_expired_index",
                "filesystem_deleted_inode",
                "slack_recovered",
                "unreferenced_carve",
                "h264_nal_tail",
                "hikbtree_deleted_entry",   # Hikvision: index cleared, data still in video area
            },
```

---

## 4. What you can rely on from my side

`HikvisionAdapter.list_recordings(image)` returns, per recording:
`channel, start_ts, end_ts, byte_offset, byte_length, event_type, resolution, fps,
allocation_state`. Field set and order are asserted by test.

`allocation_state`, `event_type`, `resolution`, `fps` and `timestamp_confidence_basis` also travel
through `validation_evidence` on every segment row, so they reach the API without a schema change.

Run `python scripts/validation/verify_engine_output.py` for a live dump of the contract against the
emulated image; `--json` gives you the raw rows to build fixtures from.

**Caveat, stated plainly:** all of this is validated against an *emulated* image built from
published research, not a real Hikvision drive — see `docs/VALIDATION-REPORT.md` §
"Hikvision validation methodology". The byte layout is faithful to [HAN2015], but do not treat
export success here as proof of field readiness.
