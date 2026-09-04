# Hikvision proprietary filesystem — offset reference

**Module owner:** Aravind R
**Applies to:** `engine/app/parsers/schemas/hikvision_fs.py`, `engine/app/parsers/hikvision.py`
**Status:** every offset below is either (a) stated in a published source, or (b) corroborated by an
independent third-party implementation that runs against genuine Hikvision drives. Nothing in the
parser is permitted to rely on an offset that is not listed in this file.

---

## 1. Sources

| Ref | Source |
|---|---|
| **[HAN2015]** | Han, J., Jeong, D., Lee, S. — *Analysis of the HIKVISION DVR File System*. ICDF2C 2015, LNICST 157, pp. 189–199. DOI 10.1007/978-3-319-25512-5_13. Primary reverse-engineering paper; source of the physical layout, master sector semantics, HIKBTREE section model, data-block entry field meanings, IDR table, and the initialization/overwriting mechanics. |
| **[HIKEXT]** | `fmpfeifer/hikextractor`, `src/hikvision_parser.py` — https://github.com/fmpfeifer/hikextractor. Working extractor used against real Hikvision DVR/NVR drives. Source of the exact numeric field offsets inside the master sector, HIKBTREE header, page header, and data-block entry. Used here as independent corroboration of [HAN2015]'s prose. |
| **[DRAG2023]** | Dragonas, E. et al. — *IoT forensics: Exploiting unexplored log records from the HIKVISION file system*. Journal of Forensic Sciences, 2023. DOI 10.1111/1556-4029.15349. Source of the system-log region pointer offsets and the `RATS` log-record signature. |
| **[MDPI2025]** | *Automated Forensic Recovery Methodology for Video Evidence from Hikvision and Dahua DVR/NVR Systems*. Information (MDPI) 16(11):983, 2025. https://www.mdpi.com/2078-2489/16/11/983. Confirms the `HIKVISION@HANGZHOU` signature-search methodology used by `manufacturer_detect`. |
| **[ITU-T-H264]** | ITU-T Rec. H.264, §7.3.2.1.1 (`seq_parameter_set_data`) and Annex E (VUI). Source of the SPS field order used to derive resolution and frame rate. |

Where [HAN2015] and [HIKEXT] describe the same field, both are cited. Where only [HIKEXT] gives a
numeric offset, the field is marked **corroboration-only** and must be re-verified the first time we
run against a real acquired drive.

---

## 2. Physical layout

Four sections, in this order on disk ([HAN2015] §2, Fig. 1):

```
0x000000  ┌──────────────────────────┐
          │ (reserved / MBR area)    │
0x000200  ├──────────────────────────┤
          │ Master Sector (256 B)    │  ← signature + all region pointers
          ├──────────────────────────┤
          │ System Logs              │  ← RATS records
          ├──────────────────────────┤
          │ Backup Master Sector     │  ← byte-identical copy [HAN2015] §2.1
          ├──────────────────────────┤
          │ Video Data Area          │  ← N data blocks; each = [video][IDR table]
          ├──────────────────────────┤
          │ HIKBTREE                 │  ← header, page list, pages, footer
          │ Backup HIKBTREE          │  ← [HAN2015] §2.4
          └──────────────────────────┘
```

Every multi-byte integer is **little-endian** ([HAN2015] §2.1).

---

## 3. Master Sector

Base offset `0x200`, size 256 bytes ([HAN2015] §2.1). All offsets below are **relative to `0x200`**.

| Rel. offset | Size | Type | Field | Source |
|---|---|---|---|---|
| `0x10` | 18 | bytes | Signature `HIKVISION@HANGZHOU` (`48 49 4B 56 49 53 49 4F 4E 40 48 41 4E 47 5A 48 4F 55`) | [HAN2015] §2.1, [HIKEXT] |
| `0x30` | 14 | bytes | Firmware/version string, e.g. `V5.00.0000000` | [HIKEXT] — corroboration-only |
| `0x48` | 8 | u64 | Hard disk capacity in bytes | [HAN2015] §2.1 (field), [HIKEXT] (offset) |
| `0x60` | 8 | u64 | Offset to system logs | [HAN2015] §2.1, [DRAG2023] (0x260 absolute) |
| `0x68` | 8 | u64 | Total size of system logs | [DRAG2023] (0x268 absolute) |
| `0x78` | 8 | u64 | Offset to video data area | [HAN2015] §2.1, [HIKEXT] |
| `0x88` | 8 | u64 | Size of one data block | [HAN2015] §2.1, [HIKEXT] |
| `0x90` | 4 | u32 | Total number of data blocks | [HAN2015] §2.1, [HIKEXT] |
| `0x98` | 8 | u64 | Offset to HIKBTREE #1 | [HAN2015] §2.1, [HIKEXT] |
| `0xA0` | 4 | u32 | Size of HIKBTREE #1 | [HAN2015] §2.1, [HIKEXT] |
| `0xA8` | 8 | u64 | Offset to HIKBTREE #2 (backup) | [HIKEXT] — corroboration-only |
| `0xB0` | 4 | u32 | Size of HIKBTREE #2 (backup) | [HIKEXT] — corroboration-only |
| `0xF0` | 4 | u32 | Time of last system initialization (UNIX, UTC) | [HAN2015] §2.1, [HIKEXT] |

### Sample values published in [HAN2015] §2.1

Used as the sanity envelope in `validate_master_block()`:

| Field | Published sample |
|---|---|
| capacity | `0x25433D6000` (≈160 GB) |
| system logs offset / size | `0x3D13200` / `0xF42C00` |
| video data area offset | `0x4C5E000` |
| data block size | `0x400000` |
| total data blocks | `0x94` |
| HIKBTREE offset / size | `0x25433BDC00` / `0x6000` |
| system init time | `0x37227754` |

> **Data block size note.** [HAN2015] §2.3 states a data block is "generally 1 GB (`0x40000000`)",
> while the §2.1 worked sample reads `0x400000` (4 MiB). Both appear in the wild depending on model
> and disk size. The parser therefore **reads** the value from `+0x88` and never assumes it, and
> `validate_master_block()` accepts any power-of-two between 1 MiB and 4 GiB.

### Forensic significance of `+0xF0`

[HAN2015] §3.2: a Hikvision DVR has **no delete function**. Initialization is the only way to erase,
and it (a) rewrites this timestamp, (b) zeroes the system logs, (c) reinitializes the HIKBTREE —
but **leaves all video data in the data blocks intact**. Any IDR-table timestamp that predates
`+0xF0` is therefore evidence of a wipe, and its footage is still carvable. This is why our engine
carves the video area independently of the index rather than trusting the index alone.

---

## 4. System Logs

Region located by master `+0x60` / `+0x68` ([DRAG2023]).

Each record begins with the constant `RATS` followed by `01 00 00 00`
(`52 41 54 53 01 00 00 00`), then a UNIX "created time", then a type byte, then a
variable-length description ([HAN2015] §2.2, Fig. 3).

| Type value | Meaning | Examples |
|---|---|---|
| `0x01` | Alarm | Start Motion Detection, Stop Motion Detection |
| `0x02` | Exception | Video Loss Alarm, Illegal Login, HDD Full |
| `0x03` | Operation | Power On/Shutdown, Login/Logout, Configure Parameters |
| `0x04` | Information | Local HDD Information, S.M.A.R.T, Start/Stop Recording |

> **Deliberate gap.** [HAN2015] Fig. 3 gives the record layout as a figure, not as a numeric table,
> and we could not obtain [DRAG2023] full text. We therefore locate `RATS` records by **signature
> scan only** and do not assert a numeric offset for the type byte or description. The engine
> consequently does **not** derive `event_type` from the system log — see §7. Close this gap against
> [DRAG2023] once a real acquired drive is available.

---

## 5. Video Data Area

Composed of `total_data_blocks` blocks of `data_block_size` bytes, starting at
`video_area_offset` ([HAN2015] §2.3).

Each data block is split into two parts ([HAN2015] §2.3, Fig. 4):

```
┌────────────────────────────────────────┬──────────────┐
│ Video data (H.264 Annex-B NAL units)   │  IDR table   │
└────────────────────────────────────────┴──────────────┘
 grows forward →                     ← grows backward from block end
```

### 5.1 Video data is H.264, not MPEG-PS

This is the single most important correction to our previous implementation.

[HAN2015] §2.3: video is H.264, each frame stored as a NAL unit identified by the 4-byte sequence
`00 00 00 01` plus a 1-byte NAL header:

| NAL type | Value | NAL type | Value |
|---|---|---|---|
| SEI | `0x06` | IDR picture | `0x65` |
| Access Unit Delimiter | `0x09` | SPS | `0x67` |
| Non-IDR picture | `0x61` | PPS | `0x68` |

**In front of each NAL unit the recorder writes a proprietary picture-index header**: the 3-byte
sequence `00 00 01` followed by `0xBA` or `0xBC` ([HAN2015] §2.3). [HAN2015] explicitly notes this
is why the footage shows noise in any player other than Hikvision's own `player.exe`.

`00 00 01 BA` is therefore a **Hikvision picture-index marker**, *not* an MPEG-PS pack header,
despite being byte-identical to one. Treating it as MPEG-PS — which the pre-refactor code did —
produces a stream no demuxer can read. `hikextractor` [HIKEXT] confirms the practical consequence:
its export path locates the first `00 00 01 BA` and writes the run to ffmpeg as **raw H.264**
(`-c:v copy -bsf:v filter_units=pass_types=1-5`), never as a program stream.

Constants in our code are named `PICTURE_INDEX_BA` / `PICTURE_INDEX_BC` for this reason. The names
`MPEG_PS_PACK` and the `wrap_mpegps()` helper were removed.

### 5.2 IDR table

At the **end** of each data block, records written in the direction of *decreasing* offset
([HAN2015] §2.3):

| Property | Value | Source |
|---|---|---|
| Record signature | `OFNI` (`4F 46 4E 49`) | [HAN2015] §2.3 |
| Record size | 56 bytes, fixed | [HAN2015] §2.3 |
| Record contents | index, channel, and timestamp of one IDR picture | [HAN2015] §2.3 |
| Direction | from block end, decreasing | [HAN2015] §2.3 |

[HAN2015] gives the record contents as a list, not as a numeric field table. Our
`parse_idr_table()` therefore locates records by the `OFNI` signature and the fixed 56-byte stride,
and recovers the timestamp by **scanning the record for a u32 that falls inside the entry's own
recorder time window** rather than asserting an uncited field offset. Every timestamp recovered this
way is tagged `timestamp_source="idr_table_scan"` so the provenance is visible in the report.

The IDR table is what makes sub-block granularity possible: [HAN2015] §2.4 notes that when several
data block entries share the *same* data-block offset, the recorder was paused or the channel
changed mid-block, and the individual recordings can only be separated by comparing IDR-table
timestamps against the entry time ranges.

---

## 6. HIKBTREE

Located by master `+0x98`. Signature `HIKBTREE` (`48 49 4B 42 54 52 45 45`) at tree `+0x10`
([HAN2015] §2.4, [HIKEXT]). Sections: header, page list, pages, footer ([HAN2015] §2.4).

### 6.1 Header

| Rel. offset | Size | Type | Field | Source |
|---|---|---|---|---|
| `0x10` | 8 | bytes | Signature `HIKBTREE` | [HAN2015] §2.4, [HIKEXT] |
| `0x58` | 8 | u64 | Offset to first page | [HIKEXT] — corroboration-only; [HAN2015] §2.4 states the field exists |

[HAN2015] §2.4 also lists a created time, a page-list pointer and a footer pointer in the header.
Numeric offsets for those three are not published and we do not read them.

### 6.2 Page

Page size is **4 KB** ([HAN2015] §2.4). Offsets relative to page start:

| Rel. offset | Size | Type | Field | Source |
|---|---|---|---|---|
| `0x10` | 4 | u32 | Number of data block entries in this page | [HIKEXT] |
| `0x20` | 8 | u64 | Offset to next page; `0xFFFFFFFFFFFFFFFF` on the last page | [HAN2015] §2.4, [HIKEXT] |
| `0x60` | — | — | Start of the data block entry array | [HIKEXT] |

[HAN2015] §2.4: "if the page is the last page, that field is written by `0xFF` hexadecimal values."
Our loop also treats `0` as a terminator and caps traversal at `MAX_PAGES` with a visited-set cycle
guard, because a corrupt or partially-overwritten index on real evidence can otherwise loop forever.

### 6.3 Data block entry

Stride **48 bytes**. Offsets relative to entry start:

| Rel. offset | Size | Type | Field | Source |
|---|---|---|---|---|
| `0x08` | 8 | u64 | **Existence of video data** (allocation flag) | [HAN2015] §2.4, [HIKEXT] |
| `0x11` | 1 | u8 | Channel number (`0x01` = camera #1) | [HAN2015] §2.4, [HIKEXT] |
| `0x18` | 4 | u32 | Start of recording (UNIX, UTC) | [HAN2015] §2.4, [HIKEXT] |
| `0x1C` | 4 | u32 | End of recording (UNIX, UTC) | [HAN2015] §2.4, [HIKEXT] |
| `0x20` | 8 | u64 | Offset to the data block | [HAN2015] §2.4, [HIKEXT] |

### 6.4 Allocation flag semantics — exact values

[HAN2015] §2.4, verbatim meaning:

* `0x00` → the data block **is full of video data**.
* `0xFF` (field filled with `0xFF` bytes) → the data block has **no video data and no recording**.

[HIKEXT] implements the allocated test as `u64 at +0x08 == 0`.

**Our pre-refactor builder wrote `1` for the unallocated case. No real recorder produces that.**
The test-only builder now writes `0x00` / `0xFFFFFFFFFFFFFFFF`, and the parser classifies on
`flag == 0` rather than on `flag == 1`.

### 6.5 Timestamp sentinel

[HAN2015] §2.4: start/end hold real UNIX times **only when the data block is full**; otherwise the
field pair reads `FF FF FF 7F 00 00 00 00` — i.e. the start u32 is `0x7FFFFFFF`.

[HIKEXT] interprets `start == 0x7FFFFFFF` on an *allocated* entry as **"currently recording"**.

Our pre-refactor `_unix_iso()` silently discarded any value `>= 0x7FFFFFFF`, so an in-progress
recording — the most operationally interesting entry on a seized live drive — was dropped without
comment. It is now surfaced as `allocation_state = "recording"`.

---

## 7. Allocation state model (Pramaan-specific classification)

The published research classifies entries into two buckets (allocated / not). For deleted-footage
recovery, which is what SIH26150 actually grades, we refine that into four states. The extra
inference is ours, but each rule is grounded in a cited fact.

| `allocation_state` | Rule | Grounding |
|---|---|---|
| `allocated` | flag `== 0` and start `!= 0x7FFFFFFF` | [HAN2015] §2.4 |
| `recording` | flag `== 0` and start `== 0x7FFFFFFF` | [HAN2015] §2.4 sentinel + [HIKEXT] |
| `deleted (index entry cleared)` | flag `!= 0` **and** `data_offset` lands inside `[video_area_offset, video_area_offset + total_data_blocks * data_block_size)` | The recorder cannot delete a file ([HAN2015] §1). Initialization clears the index but leaves video data in place ([HAN2015] §3.2). A cleared flag whose data pointer still addresses the video area is therefore a residual index entry for footage that is still on the platter. |
| `unallocated` | flag `!= 0` and `data_offset` outside the video area (typically `0`) | A slot the recorder has never used. Not evidence; not emitted as a recording. |

### 7.1 Timestamp confidence ladder

The brief requires deleted entries to carry a lower `timestamp_confidence`. To avoid reintroducing
invented numbers, confidence is a **three-value ladder with a stated basis**, and every entry also
carries `timestamp_confidence_basis` naming which rung applies and why.

| Value | `timestamp_source` | Applies to | Why this rung |
|---|---|---|---|
| `0.9` | `hikbtree_entry` | `allocated` | Flag and timestamps were written together by the recorder in the same transaction and agree with each other. |
| `0.5` | `hikbtree_residual` | `deleted (index entry cleared)` with plausible residual timestamps | The flag was cleared *after* the timestamps were written. The times may describe a recording that has since been partly or wholly overwritten, so they bound the footage but do not confirm it. |
| `0.3` | `idr_table_scan` | `deleted` whose index timestamps are the `0x7FFFFFFF` sentinel, recovered from the IDR table instead | [HAN2015] §3.3: overwriting resets start/end to the sentinel, so the only surviving time is inside the data block itself, and it may belong to either the old or the new recording. |

Both deletion modes are exercised by the emulated image and asserted by the test suite:
`test_initialised_entry_keeps_residual_timestamps` (§3.2) and
`test_overwritten_recording_recovers_its_time_from_the_idr_table` (§3.3).
`test_confidence_ladder_is_ordered` pins the three rungs and asserts no other
confidence value is emitted.

> **Which mode matters more.** On a disk that has been recording long enough to wrap,
> §3.3 overwriting is the *common* case and §3.2 initialization is the rare one. An
> engine validated only against the initialization case would look correct in the lab
> and lose the recording time on real evidence.
| `0.1` | unchanged | any entry that **contradicts itself** (§7.4, §7.5) | The recorder writes the 48 bytes of an entry as one unit, so a field that cannot be true is evidence the entry was not written coherently. That is exactly what the `0.9` basis asserts, so the assertion is withdrawn. |
| `None` | `unavailable` | no usable time from either source | — |

These are the **only** numeric confidences the Hikvision engine emits. There is no
`0.42 + count * 0.01` anywhere in this module. On an undamaged image only the top three
rungs occur; `0.1` appears solely where the index itself is self-contradictory, which
`test_confidence_ladder_is_ordered` (clean image) and `EntryIntegrityTests` (corrupt
entries) pin from opposite directions.

### 7.4 `timestamp_status` — are the entry's own times coherent?

A third axis, independent of both `allocation_state` and `recovery_status`.

| Value | Meaning |
|---|---|
| `ok` | Start and end are either absent or in order. |
| `inverted_window` | `end <= start`. The recorder cannot have written the pair consistently. |

**Raw timestamps are never repaired.** They are not swapped, clamped, or replaced with a
plausible-looking window; both values are reported exactly as found and the anomaly is
stated alongside them. Confidence drops to `0.1` and the basis names the contradiction.

> Audit finding **F-1**: before this was added, an inverted window was emitted at `0.9`
> with the basis "…written together by the recorder and mutually consistent" — a claim
> that is false precisely when the window is inverted.

### 7.5 `channel_valid` — can this byte name a camera?

The channel byte (entry `+0x11`) is a **1-based u8** ([HAN2015] §2.4, [HIKEXT]). Two values
are provably not camera numbers:

| Value | Why it cannot be a camera |
|---|---|
| `0x00` | The format numbers cameras from 1, so zero addresses none. |
| `0xFF` | The format's erase pattern — the same all-ones fill used by the cleared allocation flag (§6.4). |

**No maximum channel count is imposed.** Neither [HAN2015] nor [HIKEXT] publishes one, so
every value in `1..254` is treated as valid; inventing a ceiling would manufacture false
negatives on large NVRs. The raw byte is always preserved in `channel` — it is never
remapped to `0`, `1`, or `"unknown"` — and `channel_valid` carries the judgement.

> Audit finding **F-2**: a corrupted channel byte previously surfaced as "channel 255" at
> confidence `0.9`, indistinguishable in the UI from a real camera.

### 7.6 Index traversal status — is the inventory complete?

`walk_hikbtree()` returns a `HikbtreeTraversal` and `recover_recordings()` a
`RecoveryResult`, both carrying how the page walk ended. "6 recordings" and "6 recordings
found before the index broke" are different findings about the same disk, and an examiner
relying on the inventory has to be able to tell them apart.

| Status | Cause |
|---|---|
| `complete` | Reached a documented last page (`next = 0xFFFFFFFFFFFFFFFF` or `0`). |
| `loop` | A page pointer re-entered a page already in the chain. |
| `out_of_bounds` | A next-page pointer addressed bytes outside the image. |
| `malformed_page` | A page declared entries that run past the end of the image. |
| `page_limit` | The `MAX_PAGES` safety limit was hit with the chain still continuing. |
| `no_index` | No HIKBTREE signature, or a master sector that failed validation. |

Entries found before an abnormal stop **are retained** — safe partial recovery is the
intended design — but the status travels with them into `validation_evidence` as
`index_traversal_status`, `index_complete`, `index_traversal_detail` and
`index_pages_read`, so neither the API, the report, nor the Recovery page can present a
truncated inventory as a whole one.

> **Known limitation, deliberately not papered over.** §6.2 defines
> `0xFFFFFFFFFFFFFFFF` as the last-page marker. A next-page pointer *overwritten with that
> exact value* is therefore a valid last page as far as the format can tell, and the walk
> reports `complete`. No published field (page count, total entries) exists to cross-check
> it. `test_severed_pointer_to_the_documented_terminator_is_indistinguishable` records this
> rather than letting a later reader assume the case is detected.

> Audit finding **F-3**: every page-walk exit was previously a bare `break`, so silent
> truncation was indistinguishable from a complete read.

### 7.3 `recovery_status` — is all of it still there?

`allocation_state` describes what the **index** claims. `recovery_status` describes what the
**data** is. They are independent: a recording can be `allocated` *and* `partial` — still
indexed by the recorder, but its data block has been partly reused.

| `recovery_status` | Rule | Grounding |
|---|---|---|
| `intact` | Every IDR record in the block falls inside the entry's own start→end window | — |
| `partial` | At least one IDR record lies **outside** that window | [HAN2015] §3.3 |

[HAN2015] §3.3 gives this test directly: *"If any recording time from the IDR tables in the
video data predates the 'Start/End time of record' of data block entries, it can be understood
that the hard disk had been full at least one time and has previously been overwritten."* A
block carrying records from outside the entry's window therefore holds footage from more than
one recording.

**What `partial` does and does not mean.** It means part of this data block belongs to a
different recording, so only the bytes inside the entry's own window are this recording. The
overwritten remainder is **reported gone and never reconstructed** — no interpolation, no
padding, no guessed frames. The recording is still recovered and still exported; the examiner
is simply told it is incomplete and why, in `partial_reason`.

The check is deliberately conservative: with no usable window, or no IDR records to compare,
nothing is claimed. An absent IDR table yields `intact`, not a false `partial`.

### 7.2 `event_type` derivation

`event_type` is **not** a field in the data block entry, and the system-log type byte offset is not
citable (§4). It is therefore inferred from IDR-table cadence, using rules from [HAN2015] §2.4:

| `event_type` | Rule |
|---|---|
| `continuous` | IDR timestamps span ≥ 80 % of the entry's start→end window at a steady cadence. |
| `event` | IDR timestamps cluster into one or more short runs inside a longer entry window — the recorder only wrote on a trigger. |
| `unknown` | No readable IDR table, or fewer than two IDR records. |

`event_type` is never reported as `motion` specifically, because distinguishing motion from other
alarm classes requires the system-log type byte we cannot yet cite. Upgrade this once [DRAG2023] is
obtained.

---

## 8. Resolution and frame rate

Derived from the H.264 **SPS** (NAL type `0x67`), per [ITU-T-H264] §7.3.2.1.1 and Annex E — *not*
from any Hikvision structure and *not* from MPEG-PS headers, which do not exist here (§5.1).

1. Locate the first NAL with `nal_unit_type == 7` inside the entry's data block.
2. Strip RBSP emulation-prevention bytes (`00 00 03` → `00 00`).
3. Exp-Golomb decode to `pic_width_in_mbs_minus1` and `pic_height_in_map_units_minus1`.
4. `width  = (pic_width_in_mbs_minus1 + 1) * 16 - (crop_left + crop_right) * crop_unit_x`
   `height = (2 - frame_mbs_only_flag) * (pic_height_in_map_units_minus1 + 1) * 16 - (crop_top + crop_bottom) * crop_unit_y`
5. If VUI `timing_info_present_flag` is set: `fps = time_scale / (2 * num_units_in_tick)`.
   Otherwise `fps` is `None` — we do **not** substitute a default.

`resolution` is reported as `"WIDTHxHEIGHT"`, or `None` when no SPS is present in the block. A
deleted entry whose SPS has been overwritten legitimately yields `None`; that is a true finding and
must not be back-filled.

---

## 9. Engine output contract

`list_recordings()` returns one record per HIKBTREE entry that resolves to footage, with exactly
these keys (consumed by the Recovery menu playback pipeline):

| Key | Type | Notes |
|---|---|---|
| `channel` | `int` | entry `+0x11` |
| `start_ts` | `str \| None` | ISO-8601 UTC |
| `end_ts` | `str \| None` | ISO-8601 UTC |
| `byte_offset` | `int` | entry `+0x20`, absolute |
| `byte_length` | `int` | clamped to data block size and to image length |
| `event_type` | `str` | `continuous` \| `event` \| `unknown` (§7.2) |
| `resolution` | `str \| None` | `"WIDTHxHEIGHT"` from SPS (§8) |
| `fps` | `float \| None` | from VUI (§8) |
| `allocation_state` | `str` | §7 |
| `recovery_status` | `str` | `intact` \| `partial` (§7.3) |

`unallocated` entries are excluded — they describe no footage.

---

## 10. Memory and performance constraints (desktop / Tauri)

The engine runs in a desktop shell, against images that can be multi-terabyte.

1. **Never materialize the mapping.** `bytes(mmap)` on the whole map is forbidden. The parser takes
   an `mmap`/buffer and slices bounded windows only.
2. **Never retain raw bytes per segment.** The pre-refactor adapter held up to 512 KB of
   `raw_bytes` per segment for every entry simultaneously — on a 4 TB drive with a few thousand data
   blocks that is multiple GB resident before a single artifact is written. Segments now carry byte
   ranges; `recovery._write_bounded_artifact` re-reads from the image when writing.
3. **Never byte-scan in a Python loop.** The pre-refactor `carve_mpegps_block` ran
   `for idx in range(len(data) - 3)` over a 512 KB slice *per entry*. All scanning now uses
   `bytes.find` / `mmap.find`, which runs in C.
4. **Bound every walk.** `MAX_PAGES` plus a visited-offset set; entry counts clamped to what the
   4 KB page can physically hold.

---

## 11. Known gaps

| Gap | Blocked on |
|---|---|
| Real-hardware validation. The parser has never run against a genuine Hikvision drive; the synthetic path has instead been hardened to cover the structural cases a real drive is most likely to hit — entries spread across a chain of index pages, and a data block partly overwritten by a later recording. | A physical device. |
| No real acquired Hikvision drive. All validation runs against the emulated image built by `engine/tests/support/hikvision_builder.py`, which is stamped `emulated` in every artifact and report it produces. | Obtaining a genuine Hikvision HDD acquisition. |
| System-log (`RATS`) record field offsets — needed to promote `event_type` from `event` to a specific alarm class such as `motion`. | Full text of [DRAG2023]. |
| HIKBTREE header created-time, page-list pointer and footer pointer offsets. | Not published in [HAN2015]; would need reverse engineering against a real drive. |
| Backup master sector / backup HIKBTREE are located but not yet used for cross-validation of a damaged primary. | Real drive with a damaged index. |
