"""Hikvision proprietary filesystem parser.

Every offset in this module is documented and sourced in ``docs/reference/hikvision_fs.md``.
Do not add an offset here without adding it there first.

This module is a **parser only**. It contains no image builders: constructing a Hikvision
filesystem is a test concern and lives in ``engine/tests/support/hikvision_builder.py``. The
engine must read real data, never round-trip against structures it wrote itself.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

# --- Master sector -------------------------------------------------------------------
# docs/reference/hikvision_fs.md §3
MASTER_BLOCK_OFFSET = 0x200
MASTER_BLOCK_SIZE = 0x100
HIKVISION_SIG = b"HIKVISION@HANGZHOU"

MASTER_SIG_OFF = 0x10
MASTER_VERSION_OFF = 0x30
MASTER_VERSION_LEN = 14
MASTER_CAPACITY_OFF = 0x48
MASTER_LOG_OFF = 0x60
MASTER_LOG_SIZE_OFF = 0x68
MASTER_VIDEO_AREA_OFF = 0x78
MASTER_DATA_BLOCK_SIZE_OFF = 0x88
MASTER_TOTAL_BLOCKS_OFF = 0x90
MASTER_HIKBTREE_OFF = 0x98
MASTER_HIKBTREE_SIZE_OFF = 0xA0
MASTER_HIKBTREE2_OFF = 0xA8
MASTER_HIKBTREE2_SIZE_OFF = 0xB0
MASTER_INIT_TIME_OFF = 0xF0

# --- HIKBTREE ------------------------------------------------------------------------
# docs/reference/hikvision_fs.md §6
HIKBTREE_SIG = b"HIKBTREE"
TREE_SIG_OFF = 0x10
TREE_FIRST_PAGE_OFF = 0x58

PAGE_SIZE = 0x1000
PAGE_ENTRY_COUNT_OFF = 0x10
PAGE_NEXT_PAGE_OFF = 0x20
PAGE_ENTRY_BASE = 0x60

ENTRY_SIZE = 48
ENTRY_ALLOC_FLAG_OFF = 0x08
ENTRY_CHANNEL_OFF = 0x11
ENTRY_START_TS_OFF = 0x18
ENTRY_END_TS_OFF = 0x1C
ENTRY_DATA_OFFSET_OFF = 0x20

MAX_ENTRIES_PER_PAGE = (PAGE_SIZE - PAGE_ENTRY_BASE) // ENTRY_SIZE
MAX_PAGES = 65536
PAGE_TERMINATORS = frozenset({0, 0xFFFFFFFFFFFFFFFF})

# §6.4 — 0x00 means "data block is full of video data"; a non-zero (0xFF-filled) flag means
# the recorder considers the block empty.
ALLOC_FLAG_ALLOCATED = 0

# §6.5 — start/end read FF FF FF 7F 00 00 00 00 when the block is not full.
TIME_SENTINEL = 0x7FFFFFFF

# --- Video data ----------------------------------------------------------------------
# docs/reference/hikvision_fs.md §5
#
# NOTE: 00 00 01 BA is Hikvision's proprietary *picture-index* header, NOT an MPEG-PS pack
# header, despite being byte-identical to one ([HAN2015] §2.3). The payload behind it is raw
# H.264 Annex-B. Do not reintroduce an MPEG-PS wrapper here.
PICTURE_INDEX_BA = b"\x00\x00\x01\xba"
PICTURE_INDEX_BC = b"\x00\x00\x01\xbc"
NAL_START_4 = b"\x00\x00\x00\x01"
IDR_TABLE_SIG = b"OFNI"
IDR_RECORD_SIZE = 56
IDR_TABLE_SCAN_BYTES = 256 * 1024

# Plausibility envelope for a residual UNIX timestamp recovered from a cleared index entry.
# 2000-01-01 .. 2038-01-01. Anything outside is structural noise, not a recorder time.
MIN_PLAUSIBLE_UNIX = 946_684_800
MAX_PLAUSIBLE_UNIX = 2_145_916_800

# --- Allocation states ---------------------------------------------------------------
# docs/reference/hikvision_fs.md §7
STATE_ALLOCATED = "allocated"
STATE_RECORDING = "recording"
STATE_DELETED = "deleted (index entry cleared)"
STATE_UNALLOCATED = "unallocated"

# §7.1 — the only numeric confidences this engine emits, each with a stated basis.
CONFIDENCE_INDEXED = 0.9
CONFIDENCE_RESIDUAL = 0.5
CONFIDENCE_IDR_SCAN = 0.3

SOURCE_INDEXED = "hikbtree_entry"
SOURCE_RESIDUAL = "hikbtree_residual"
SOURCE_IDR_SCAN = "idr_table_scan"
SOURCE_UNAVAILABLE = "unavailable"

# --- Recovery status ------------------------------------------------------------------
# docs/reference/hikvision_fs.md section 7.3
#
# Separate axis from allocation_state: allocation_state describes what the *index*
# says, recovery_status describes what the *data* is. A recording can be
# allocated+partial (still indexed, but its block has been partly overwritten) or
# deleted+partial. Bytes that are gone are reported gone, never reconstructed.
RECOVERY_INTACT = "intact"
RECOVERY_PARTIAL = "partial"

EVENT_CONTINUOUS = "continuous"
EVENT_EVENT = "event"
EVENT_UNKNOWN = "unknown"

# §7.2 — an entry whose IDR timestamps cover this fraction of its declared window was
# recording continuously; anything less was trigger-driven.
CONTINUOUS_COVERAGE_RATIO = 0.8


class HikvisionFormatError(ValueError):
    """Raised when a structure carries the right signature but impossible field values."""


# --------------------------------------------------------------------------------------
# Low-level readers
# --------------------------------------------------------------------------------------

Buffer = "bytes | bytearray | memoryview"


def _u8(data, offset: int) -> int:
    return data[offset]


def _u32(data, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _fits(data, offset: int, length: int) -> bool:
    return offset >= 0 and length >= 0 and offset + length <= len(data)


def unix_to_iso(value: int | None) -> str | None:
    """UNIX seconds (UTC) to ISO-8601, or None when the value is not a usable time."""
    if value is None or not (0 < value < TIME_SENTINEL):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _plausible_unix(value: int) -> bool:
    return MIN_PLAUSIBLE_UNIX <= value <= MAX_PLAUSIBLE_UNIX


# --------------------------------------------------------------------------------------
# Master sector — docs/reference/hikvision_fs.md §3
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MasterBlock:
    signature: bytes
    version: str
    capacity: int
    log_offset: int
    log_size: int
    video_area_offset: int
    data_block_size: int
    total_data_blocks: int
    hikbtree_offset: int
    hikbtree_size: int
    hikbtree_backup_offset: int
    hikbtree_backup_size: int
    init_time_unix: int

    @property
    def video_area_end(self) -> int:
        return self.video_area_offset + self.data_block_size * self.total_data_blocks

    @property
    def init_time_iso(self) -> str | None:
        return unix_to_iso(self.init_time_unix)

    def contains_video(self, offset: int) -> bool:
        """True when ``offset`` addresses a byte inside the declared video data area."""
        if self.data_block_size <= 0 or self.total_data_blocks <= 0:
            return False
        return self.video_area_offset <= offset < self.video_area_end


def parse_master_block(data, offset: int = MASTER_BLOCK_OFFSET) -> MasterBlock | None:
    """Parse the master sector at ``offset``. Returns None when the signature is absent."""
    if not _fits(data, offset, MASTER_BLOCK_SIZE):
        return None
    sig_start = offset + MASTER_SIG_OFF
    if bytes(data[sig_start : sig_start + len(HIKVISION_SIG)]) != HIKVISION_SIG:
        return None

    version_raw = bytes(data[offset + MASTER_VERSION_OFF : offset + MASTER_VERSION_OFF + MASTER_VERSION_LEN])
    return MasterBlock(
        signature=HIKVISION_SIG,
        version=version_raw.split(b"\x00", 1)[0].decode("ascii", "replace"),
        capacity=_u64(data, offset + MASTER_CAPACITY_OFF),
        log_offset=_u64(data, offset + MASTER_LOG_OFF),
        log_size=_u64(data, offset + MASTER_LOG_SIZE_OFF),
        video_area_offset=_u64(data, offset + MASTER_VIDEO_AREA_OFF),
        data_block_size=_u64(data, offset + MASTER_DATA_BLOCK_SIZE_OFF),
        total_data_blocks=_u32(data, offset + MASTER_TOTAL_BLOCKS_OFF),
        hikbtree_offset=_u64(data, offset + MASTER_HIKBTREE_OFF),
        hikbtree_size=_u32(data, offset + MASTER_HIKBTREE_SIZE_OFF),
        hikbtree_backup_offset=_u64(data, offset + MASTER_HIKBTREE2_OFF),
        hikbtree_backup_size=_u32(data, offset + MASTER_HIKBTREE2_SIZE_OFF),
        init_time_unix=_u32(data, offset + MASTER_INIT_TIME_OFF),
    )


def validate_master_block(master: MasterBlock) -> list[str]:
    """Return a list of structural problems. Empty list means the master sector is sane.

    Bounds come from the sample values published in [HAN2015] §2.1 — see
    docs/reference/hikvision_fs.md §3. This exists so a corrupt or misidentified image fails
    loudly instead of driving a multi-terabyte walk off a garbage pointer.
    """
    problems: list[str] = []
    size = master.data_block_size
    if not (1 << 20) <= size <= (1 << 32) or size & (size - 1):
        problems.append(f"data_block_size {size:#x} is not a power of two between 1MiB and 4GiB")
    if master.total_data_blocks <= 0:
        problems.append("total_data_blocks is zero")
    if master.video_area_offset <= MASTER_BLOCK_OFFSET:
        problems.append(f"video_area_offset {master.video_area_offset:#x} overlaps the master sector")
    if master.hikbtree_offset <= MASTER_BLOCK_OFFSET:
        problems.append(f"hikbtree_offset {master.hikbtree_offset:#x} overlaps the master sector")
    return problems


def find_master_block(data, *, search_bytes: int = 1 << 20) -> int | None:
    """Locate the master sector.

    Tries the documented ``0x200`` first, then falls back to a bounded signature scan so a
    partition-offset acquisition (image starts at the partition, not the disk) still parses.
    """
    if parse_master_block(data, MASTER_BLOCK_OFFSET) is not None:
        return MASTER_BLOCK_OFFSET
    limit = min(len(data), search_bytes)
    hit = data.find(HIKVISION_SIG, 0, limit)
    if hit < 0:
        return None
    candidate = hit - MASTER_SIG_OFF
    if candidate < 0 or parse_master_block(data, candidate) is None:
        return None
    return candidate


# --------------------------------------------------------------------------------------
# HIKBTREE — docs/reference/hikvision_fs.md §6, §7
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HikbtreeEntry:
    channel: int
    start_unix: int | None
    end_unix: int | None
    data_offset: int
    allocation_state: str
    alloc_flag: int
    page_offset: int
    entry_index: int
    timestamp_source: str
    timestamp_confidence: float | None
    timestamp_confidence_basis: str

    @property
    def is_deleted(self) -> bool:
        return self.allocation_state == STATE_DELETED

    @property
    def has_footage(self) -> bool:
        """True when this entry describes footage on the platter (allocated, live, or deleted)."""
        return self.allocation_state != STATE_UNALLOCATED

    @property
    def start_iso(self) -> str | None:
        return unix_to_iso(self.start_unix)

    @property
    def end_iso(self) -> str | None:
        return unix_to_iso(self.end_unix)


def _classify_entry(
    *,
    alloc_flag: int,
    start_raw: int,
    end_raw: int,
    data_offset: int,
    master: MasterBlock | None,
) -> tuple[str, int | None, int | None, str, float | None, str]:
    """Return (state, start, end, timestamp_source, confidence, basis).

    Classification rules and their grounding: docs/reference/hikvision_fs.md §7.
    """
    allocated = alloc_flag == ALLOC_FLAG_ALLOCATED

    if allocated:
        if start_raw == TIME_SENTINEL:
            # §6.5 / [HIKEXT]: an allocated entry with the sentinel is an in-progress recording.
            return (
                STATE_RECORDING,
                None,
                None,
                SOURCE_INDEXED,
                CONFIDENCE_INDEXED,
                "allocated entry with 0x7FFFFFFF start sentinel: recording in progress, no end time written yet",
            )
        return (
            STATE_ALLOCATED,
            start_raw or None,
            end_raw or None,
            SOURCE_INDEXED,
            CONFIDENCE_INDEXED,
            "allocation flag and timestamps written together by the recorder and mutually consistent",
        )

    # Flag cleared. Does the data pointer still address the video area?
    points_into_video = master.contains_video(data_offset) if master is not None else data_offset > 0
    if not points_into_video:
        return (
            STATE_UNALLOCATED,
            None,
            None,
            SOURCE_UNAVAILABLE,
            None,
            "index slot never used by the recorder",
        )

    if _plausible_unix(start_raw):
        return (
            STATE_DELETED,
            start_raw,
            end_raw if _plausible_unix(end_raw) else None,
            SOURCE_RESIDUAL,
            CONFIDENCE_RESIDUAL,
            "index flag cleared after timestamps were written; residual times bound the footage "
            "but may describe a recording since partly overwritten",
        )

    return (
        STATE_DELETED,
        None,
        None,
        SOURCE_UNAVAILABLE,
        None,
        "index flag cleared and timestamps reset to the 0x7FFFFFFF sentinel; recover time from the IDR table",
    )


def parse_hikbtree_entries(
    data,
    tree_offset: int,
    *,
    master: MasterBlock | None = None,
    include_unallocated: bool = False,
) -> list[HikbtreeEntry]:
    """Walk the HIKBTREE page chain and return its data block entries.

    ``master`` is required to distinguish a *deleted* entry (flag cleared, data pointer still
    inside the video area) from an *unallocated* one. Without it the parser degrades to the
    weaker ``data_offset > 0`` heuristic and says so via each entry's confidence basis.
    """
    if not _fits(data, tree_offset, TREE_FIRST_PAGE_OFF + 8):
        return []
    sig_at = tree_offset + TREE_SIG_OFF
    if bytes(data[sig_at : sig_at + len(HIKBTREE_SIG)]) != HIKBTREE_SIG:
        return []

    page_offset = _u64(data, tree_offset + TREE_FIRST_PAGE_OFF)
    entries: list[HikbtreeEntry] = []
    visited: set[int] = set()

    while page_offset not in PAGE_TERMINATORS and len(visited) < MAX_PAGES:
        if page_offset in visited:
            break  # corrupt index looping back on itself
        visited.add(page_offset)
        if not _fits(data, page_offset, PAGE_ENTRY_BASE):
            break

        count = _u32(data, page_offset + PAGE_ENTRY_COUNT_OFF)
        next_page = _u64(data, page_offset + PAGE_NEXT_PAGE_OFF)
        entry_base = page_offset + PAGE_ENTRY_BASE

        for index in range(min(count, MAX_ENTRIES_PER_PAGE)):
            base = entry_base + index * ENTRY_SIZE
            if not _fits(data, base, ENTRY_SIZE):
                break
            alloc_flag = _u64(data, base + ENTRY_ALLOC_FLAG_OFF)
            channel = _u8(data, base + ENTRY_CHANNEL_OFF)
            start_raw = _u32(data, base + ENTRY_START_TS_OFF)
            end_raw = _u32(data, base + ENTRY_END_TS_OFF)
            data_offset = _u64(data, base + ENTRY_DATA_OFFSET_OFF)

            state, start, end, source, confidence, basis = _classify_entry(
                alloc_flag=alloc_flag,
                start_raw=start_raw,
                end_raw=end_raw,
                data_offset=data_offset,
                master=master,
            )
            if state == STATE_UNALLOCATED and not include_unallocated:
                continue
            entries.append(
                HikbtreeEntry(
                    channel=channel,
                    start_unix=start,
                    end_unix=end,
                    data_offset=data_offset,
                    allocation_state=state,
                    alloc_flag=alloc_flag,
                    page_offset=page_offset,
                    entry_index=index,
                    timestamp_source=source,
                    timestamp_confidence=confidence,
                    timestamp_confidence_basis=basis,
                )
            )

        page_offset = next_page

    return entries


# --------------------------------------------------------------------------------------
# Video data — docs/reference/hikvision_fs.md §5
# --------------------------------------------------------------------------------------


def find_picture_index_starts(data, start: int, end: int, *, limit: int = 4096) -> list[int]:
    """Absolute offsets of Hikvision picture-index headers in ``data[start:end]``.

    Uses ``find`` (C-level) rather than a Python byte loop: this runs once per data block on
    images that can be terabytes. See docs/reference/hikvision_fs.md §10.3.
    """
    hits: list[int] = []
    cursor = start
    while len(hits) < limit:
        ba = data.find(PICTURE_INDEX_BA, cursor, end)
        bc = data.find(PICTURE_INDEX_BC, cursor, end)
        candidates = [pos for pos in (ba, bc) if pos >= 0]
        if not candidates:
            break
        hit = min(candidates)
        hits.append(hit)
        cursor = hit + 4
    return hits


def video_payload_span(data, block_start: int, block_end: int) -> tuple[int, int] | None:
    """Byte span of the H.264 payload inside one data block.

    Starts at the first picture-index header (or bare NAL start code) and runs to the start of
    the IDR table when one is present, otherwise to the end of the block.
    """
    if block_end <= block_start:
        return None
    first = data.find(PICTURE_INDEX_BA, block_start, block_end)
    if first < 0:
        first = data.find(PICTURE_INDEX_BC, block_start, block_end)
    if first < 0:
        first = data.find(NAL_START_4, block_start, block_end)
    if first < 0:
        return None

    table_start = _idr_table_start(data, block_start, block_end)
    end = table_start if table_start is not None and table_start > first else block_end
    end = _trim_trailing_zeros(data, first, end)
    if end <= first:
        return None
    return (first, end)


def _trim_trailing_zeros(data, start: int, end: int, *, window: int = 64 * 1024, max_windows: int = 256) -> int:
    """Drop the unwritten tail of a partially-filled data block.

    A data block the recorder never filled is zero-padded between the last picture and the IDR
    table. Including that padding in the extent would have the export path write megabytes of
    zeros per recording. Scanned backwards a window at a time so this stays bounded on a
    multi-terabyte image.
    """
    cursor = end
    for _ in range(max_windows):
        if cursor <= start:
            return start
        chunk_start = max(start, cursor - window)
        chunk = bytes(data[chunk_start:cursor]).rstrip(b"\x00")
        if chunk:
            return chunk_start + len(chunk)
        cursor = chunk_start
    return cursor


def _idr_table_start(data, block_start: int, block_end: int) -> int | None:
    """Offset of the lowest ``OFNI`` record in the block's trailing IDR table.

    [HAN2015] §2.3: records are written backwards from the end of the data block with a fixed
    56-byte stride. Only the tail is scanned, never the whole block.
    """
    scan_from = max(block_start, block_end - IDR_TABLE_SCAN_BYTES)
    first = data.find(IDR_TABLE_SIG, scan_from, block_end)
    return first if first >= 0 else None


def parse_idr_table(data, block_start: int, block_end: int, *, limit: int = 8192) -> list[int]:
    """Absolute offsets of the ``OFNI`` records in this block's IDR table."""
    start = _idr_table_start(data, block_start, block_end)
    if start is None:
        return []
    records: list[int] = []
    cursor = start
    while cursor + IDR_RECORD_SIZE <= block_end and len(records) < limit:
        if bytes(data[cursor : cursor + 4]) != IDR_TABLE_SIG:
            break
        records.append(cursor)
        cursor += IDR_RECORD_SIZE
    return records


def idr_timestamps(
    data,
    block_start: int,
    block_end: int,
    *,
    window: tuple[int, int] | None = None,
) -> list[int]:
    """UNIX timestamps recovered from the block's IDR table.

    [HAN2015] §2.3 lists an IDR record as carrying index, channel and timestamp but publishes
    no numeric field table (see docs/reference/hikvision_fs.md §5.2). We therefore scan each
    56-byte record for a u32 that is a plausible recorder time, optionally constrained to the
    entry's own declared window, rather than asserting an uncited field offset. Provenance is
    reported as ``idr_table_scan`` so this inference is visible in the report.
    """
    lo, hi = window if window else (MIN_PLAUSIBLE_UNIX, MAX_PLAUSIBLE_UNIX)
    found: list[int] = []
    for record in parse_idr_table(data, block_start, block_end):
        for pos in range(4, IDR_RECORD_SIZE - 3, 4):
            if not _fits(data, record + pos, 4):
                break
            value = _u32(data, record + pos)
            if lo <= value <= hi:
                found.append(value)
                break
    return sorted(found)


# --------------------------------------------------------------------------------------
# H.264 SPS — docs/reference/hikvision_fs.md §8
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamInfo:
    width: int | None
    height: int | None
    fps: float | None

    @property
    def resolution(self) -> str | None:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None


class _BitReader:
    """MSB-first bit reader over an RBSP payload."""

    __slots__ = ("_data", "_pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def bit(self) -> int:
        index = self._pos >> 3
        if index >= len(self._data):
            raise HikvisionFormatError("SPS truncated")
        value = (self._data[index] >> (7 - (self._pos & 7))) & 1
        self._pos += 1
        return value

    def bits(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | self.bit()
        return value

    def ue(self) -> int:
        """Unsigned Exp-Golomb ([ITU-T-H264] §9.1)."""
        leading = 0
        while self.bit() == 0:
            leading += 1
            if leading > 32:
                raise HikvisionFormatError("malformed Exp-Golomb code")
        if leading == 0:
            return 0
        return (1 << leading) - 1 + self.bits(leading)

    def se(self) -> int:
        """Signed Exp-Golomb ([ITU-T-H264] §9.1)."""
        value = self.ue()
        return (value + 1) // 2 if value % 2 else -(value // 2)


def _rbsp(payload: bytes) -> bytes:
    """Strip emulation-prevention bytes: 00 00 03 -> 00 00 ([ITU-T-H264] §7.4.1)."""
    out = bytearray()
    zeros = 0
    for byte in payload:
        if zeros == 2 and byte == 0x03:
            zeros = 0
            continue
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


_HIGH_PROFILES = frozenset({100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135})


def parse_sps(nal_payload: bytes) -> StreamInfo | None:
    """Decode resolution and frame rate from an H.264 SPS NAL payload (header byte excluded)."""
    try:
        reader = _BitReader(_rbsp(nal_payload))
        profile_idc = reader.bits(8)
        reader.bits(8)  # constraint flags + reserved
        reader.bits(8)  # level_idc
        reader.ue()  # seq_parameter_set_id

        chroma_format_idc = 1
        if profile_idc in _HIGH_PROFILES:
            chroma_format_idc = reader.ue()
            if chroma_format_idc == 3:
                reader.bit()  # separate_colour_plane_flag
            reader.ue()  # bit_depth_luma_minus8
            reader.ue()  # bit_depth_chroma_minus8
            reader.bit()  # qpprime_y_zero_transform_bypass_flag
            if reader.bit():  # seq_scaling_matrix_present_flag
                count = 8 if chroma_format_idc != 3 else 12
                for i in range(count):
                    if reader.bit():
                        _skip_scaling_list(reader, 16 if i < 6 else 64)

        reader.ue()  # log2_max_frame_num_minus4
        pic_order_cnt_type = reader.ue()
        if pic_order_cnt_type == 0:
            reader.ue()  # log2_max_pic_order_cnt_lsb_minus4
        elif pic_order_cnt_type == 1:
            reader.bit()  # delta_pic_order_always_zero_flag
            reader.se()  # offset_for_non_ref_pic
            reader.se()  # offset_for_top_to_bottom_field
            for _ in range(reader.ue()):
                reader.se()

        reader.ue()  # max_num_ref_frames
        reader.bit()  # gaps_in_frame_num_value_allowed_flag
        pic_width_in_mbs_minus1 = reader.ue()
        pic_height_in_map_units_minus1 = reader.ue()
        frame_mbs_only_flag = reader.bit()
        if not frame_mbs_only_flag:
            reader.bit()  # mb_adaptive_frame_field_flag
        reader.bit()  # direct_8x8_inference_flag

        crop_left = crop_right = crop_top = crop_bottom = 0
        if reader.bit():  # frame_cropping_flag
            crop_left = reader.ue()
            crop_right = reader.ue()
            crop_top = reader.ue()
            crop_bottom = reader.ue()

        width = (pic_width_in_mbs_minus1 + 1) * 16
        height = (2 - frame_mbs_only_flag) * (pic_height_in_map_units_minus1 + 1) * 16

        sub_width_c, sub_height_c = {0: (1, 1), 1: (2, 2), 2: (2, 1), 3: (1, 1)}.get(chroma_format_idc, (2, 2))
        crop_unit_x = 1 if chroma_format_idc == 0 else sub_width_c
        crop_unit_y = (2 - frame_mbs_only_flag) * (1 if chroma_format_idc == 0 else sub_height_c)
        width -= (crop_left + crop_right) * crop_unit_x
        height -= (crop_top + crop_bottom) * crop_unit_y

        fps: float | None = None
        if reader.bit():  # vui_parameters_present_flag
            fps = _vui_frame_rate(reader)

        if width <= 0 or height <= 0:
            return None
        return StreamInfo(width=width, height=height, fps=fps)
    except (HikvisionFormatError, IndexError):
        return None


def _skip_scaling_list(reader: _BitReader, size: int) -> None:
    last_scale = next_scale = 8
    for _ in range(size):
        if next_scale != 0:
            next_scale = (last_scale + reader.se() + 256) % 256
        last_scale = last_scale if next_scale == 0 else next_scale


def _vui_frame_rate(reader: _BitReader) -> float | None:
    """Read VUI far enough to reach timing_info ([ITU-T-H264] Annex E.1.1)."""
    if reader.bit():  # aspect_ratio_info_present_flag
        if reader.bits(8) == 255:  # Extended_SAR
            reader.bits(16)
            reader.bits(16)
    if reader.bit():  # overscan_info_present_flag
        reader.bit()
    if reader.bit():  # video_signal_type_present_flag
        reader.bits(3)
        reader.bit()
        if reader.bit():  # colour_description_present_flag
            reader.bits(24)
    if reader.bit():  # chroma_loc_info_present_flag
        reader.ue()
        reader.ue()
    if not reader.bit():  # timing_info_present_flag
        return None
    num_units_in_tick = reader.bits(32)
    time_scale = reader.bits(32)
    if num_units_in_tick <= 0 or time_scale <= 0:
        return None
    fps = time_scale / (2.0 * num_units_in_tick)
    return round(fps, 3) if 0 < fps <= 240 else None


def find_stream_info(data, start: int, end: int, *, scan_bytes: int = 1 << 20) -> StreamInfo | None:
    """Locate the first SPS in ``data[start:end]`` and decode it.

    Only the first ``scan_bytes`` of the span are searched: SPS is emitted at the head of every
    GOP, so a hit further in adds nothing but cost.
    """
    limit = min(end, start + scan_bytes)
    cursor = start
    while cursor < limit:
        hit = data.find(NAL_START_4, cursor, limit)
        if hit < 0:
            hit = data.find(b"\x00\x00\x01", cursor, limit)
            if hit < 0:
                return None
            header_at = hit + 3
        else:
            header_at = hit + 4
        if header_at >= limit:
            return None
        header = _u8(data, header_at)
        if header & 0x1F == 7:  # SPS
            payload_end = min(header_at + 1 + 512, end)
            info = parse_sps(bytes(data[header_at + 1 : payload_end]))
            if info is not None:
                return info
        cursor = header_at + 1
    return None


# --------------------------------------------------------------------------------------
# Event classification — docs/reference/hikvision_fs.md §7.2
# --------------------------------------------------------------------------------------


def detect_partial_overwrite(
    stamps: Sequence[int],
    start_unix: int | None,
    end_unix: int | None,
) -> tuple[bool, str]:
    """Decide whether this data block holds footage from more than one recording.

    [HAN2015] section 3.3 gives the test directly: when the disk wraps, new video is
    written over an old data block, and "if any recording time from the IDR tables in
    the video data predates the Start/End time of record of data block entries, it can
    be understood that the hard disk had been full at least one time and has previously
    been overwritten."

    So an IDR timestamp lying outside the entry's own declared window means part of
    this block belongs to a different recording. Only the portion inside the window is
    genuinely this recording; the rest is reported as lost, never reconstructed.

    Returns (is_partial, reason). Requires a usable window and at least one IDR record;
    with neither there is nothing to compare and the block is not claimed partial.
    """
    if start_unix is None or end_unix is None or not stamps:
        return False, ""
    outside = [ts for ts in stamps if ts < start_unix or ts > end_unix]
    if not outside:
        return False, ""
    older = sum(1 for ts in outside if ts < start_unix)
    newer = len(outside) - older
    parts = []
    if older:
        parts.append(f"{older} IDR record(s) predate the entry's start time")
    if newer:
        parts.append(f"{newer} IDR record(s) postdate the entry's end time")
    return True, (
        ", ".join(parts)
        + " — the data block holds footage from more than one recording "
        "([HAN2015] section 3.3). Only the bytes inside the entry's own window are "
        "reported as recovered; the remainder is overwritten and is not reconstructed."
    )


def classify_event_type(timestamps: Sequence[int], start_unix: int | None, end_unix: int | None) -> str:
    """Infer continuous vs trigger-driven recording from IDR cadence."""
    if len(timestamps) < 2:
        return EVENT_UNKNOWN
    if start_unix is None or end_unix is None or end_unix <= start_unix:
        return EVENT_UNKNOWN
    covered = timestamps[-1] - timestamps[0]
    declared = end_unix - start_unix
    return EVENT_CONTINUOUS if covered >= declared * CONTINUOUS_COVERAGE_RATIO else EVENT_EVENT


# --------------------------------------------------------------------------------------
# Engine output contract — docs/reference/hikvision_fs.md §9
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordingEntry:
    """One recovered recording. Field set is the contract with the playback pipeline."""

    channel: int
    start_ts: str | None
    end_ts: str | None
    byte_offset: int
    byte_length: int
    event_type: str
    resolution: str | None
    fps: float | None
    allocation_state: str
    recovery_status: str = RECOVERY_INTACT
    # Provenance — not part of the contract, carried for the report and custody trail.
    timestamp_source: str = SOURCE_UNAVAILABLE
    timestamp_confidence: float | None = None
    timestamp_confidence_basis: str = ""
    partial_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "channel": self.channel,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "byte_offset": self.byte_offset,
            "byte_length": self.byte_length,
            "event_type": self.event_type,
            "resolution": self.resolution,
            "fps": self.fps,
            "allocation_state": self.allocation_state,
            "recovery_status": self.recovery_status,
        }


def build_recording(data, entry: HikbtreeEntry, master: MasterBlock) -> RecordingEntry | None:
    """Resolve one HIKBTREE entry into a recording, reading metadata from the data block."""
    if entry.allocation_state == STATE_UNALLOCATED:
        return None
    block_start = entry.data_offset
    if block_start <= 0 or block_start >= len(data):
        return None
    block_end = min(len(data), block_start + master.data_block_size)

    span = video_payload_span(data, block_start, block_end)
    if span is None:
        # No decodable payload at the pointer: the block was reused or the pointer is stale.
        return None
    payload_start, payload_end = span

    start_unix, end_unix = entry.start_unix, entry.end_unix
    source = entry.timestamp_source
    confidence = entry.timestamp_confidence
    basis = entry.timestamp_confidence_basis

    window = (start_unix, end_unix) if start_unix and end_unix else None
    stamps = idr_timestamps(data, block_start, block_end, window=window)

    if start_unix is None and stamps:
        # Index times were wiped; the IDR table is the only surviving clock.
        start_unix, end_unix = stamps[0], stamps[-1]
        source = SOURCE_IDR_SCAN
        confidence = CONFIDENCE_IDR_SCAN
        basis = (
            "index timestamps reset to sentinel; times recovered from the data block's IDR "
            "table and may belong to either the original or an overwriting recording"
        )

    # A block holding IDR records from outside this entry's window carries footage
    # from more than one recording ([HAN2015] section 3.3). Report what is genuinely
    # this recording and say plainly that the rest is gone.
    #
    # This has to read the IDR table *unfiltered*: `stamps` above was constrained to
    # the entry's own window for event classification, which by construction discards
    # exactly the out-of-window records that prove an overwrite.
    all_stamps = idr_timestamps(data, block_start, block_end)
    is_partial, partial_reason = detect_partial_overwrite(
        all_stamps, start_unix, end_unix
    )

    info = find_stream_info(data, payload_start, payload_end)
    return RecordingEntry(
        channel=entry.channel,
        start_ts=unix_to_iso(start_unix),
        end_ts=unix_to_iso(end_unix),
        byte_offset=payload_start,
        byte_length=max(0, payload_end - payload_start),
        event_type=classify_event_type(stamps, start_unix, end_unix),
        resolution=info.resolution if info else None,
        fps=info.fps if info else None,
        allocation_state=entry.allocation_state,
        recovery_status=RECOVERY_PARTIAL if is_partial else RECOVERY_INTACT,
        timestamp_source=source,
        timestamp_confidence=confidence,
        timestamp_confidence_basis=basis,
        partial_reason=partial_reason,
    )


def list_recordings(data) -> list[RecordingEntry]:
    """Parse a mapped Hikvision image into recordings.

    ``data`` may be an ``mmap``, ``bytes`` or ``memoryview``. The whole mapping is never
    materialized — see docs/reference/hikvision_fs.md §10.
    """
    master_offset = find_master_block(data)
    if master_offset is None:
        return []
    master = parse_master_block(data, master_offset)
    if master is None or validate_master_block(master):
        return []

    recordings: list[RecordingEntry] = []
    for entry in parse_hikbtree_entries(data, master.hikbtree_offset, master=master):
        recording = build_recording(data, entry, master)
        if recording is not None:
            recordings.append(recording)
    recordings.sort(key=lambda item: (item.channel, item.byte_offset))
    return recordings


def summarize(recordings: Iterable[RecordingEntry]) -> dict[str, int]:
    """Counts by allocation state, for the Recovery header and the report."""
    counts: dict[str, int] = {}
    for recording in recordings:
        counts[recording.allocation_state] = counts.get(recording.allocation_state, 0) + 1
    return counts


def count_partial(recordings: Iterable[RecordingEntry]) -> int:
    """How many recovered recordings are only partially present on the platter."""
    return sum(1 for r in recordings if r.recovery_status == RECOVERY_PARTIAL)
