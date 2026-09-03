"""Test-only Hikvision filesystem image builder — EMULATED EVIDENCE.

This module exists so the parser can be validated in the absence of a genuine acquired
Hikvision drive. It is **test support and nothing else**:

* It must never be imported by ``engine/app``. The engine parses real data.
* Every image it produces is stamped ``EMULATION_STAMP`` in the reserved sector, and
  :func:`build_emulated_image` returns a manifest whose ``provenance`` is ``"emulated"``.
  Anything downstream that surfaces a recording sourced from here must say so.

The layout is built from the published research (``docs/reference/hikvision_fs.md``) rather
than from the parser's own constants where the two could drift — in particular the allocation
flag values (``0x00`` / ``0xFF``-filled) and the 4 KB page size, both of which the previous
in-engine builder got wrong and then round-tripped against itself.

Replace this with a real acquisition as soon as one is available; the parser API does not
change when you do.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from engine.app.parsers.schemas.hikvision_fs import (
    ENTRY_ALLOC_FLAG_OFF,
    ENTRY_CHANNEL_OFF,
    ENTRY_DATA_OFFSET_OFF,
    ENTRY_END_TS_OFF,
    ENTRY_SIZE,
    ENTRY_START_TS_OFF,
    HIKBTREE_SIG,
    HIKVISION_SIG,
    IDR_RECORD_SIZE,
    IDR_TABLE_SIG,
    MASTER_BLOCK_OFFSET,
    MASTER_CAPACITY_OFF,
    MASTER_DATA_BLOCK_SIZE_OFF,
    MASTER_HIKBTREE2_OFF,
    MASTER_HIKBTREE2_SIZE_OFF,
    MASTER_HIKBTREE_OFF,
    MASTER_HIKBTREE_SIZE_OFF,
    MASTER_INIT_TIME_OFF,
    MASTER_LOG_OFF,
    MASTER_LOG_SIZE_OFF,
    MASTER_SIG_OFF,
    MASTER_TOTAL_BLOCKS_OFF,
    MASTER_VERSION_OFF,
    MASTER_VIDEO_AREA_OFF,
    PAGE_ENTRY_BASE,
    PAGE_ENTRY_COUNT_OFF,
    PAGE_NEXT_PAGE_OFF,
    PAGE_SIZE,
    PICTURE_INDEX_BA,
    TIME_SENTINEL,
    TREE_FIRST_PAGE_OFF,
    TREE_SIG_OFF,
)
from engine.app.verification.media_fixture import get_nal_source, split_annexb_nals

EMULATION_STAMP = b"PRAMAAN-EMULATED-HIKVISION-FS"

# --- Geometry -------------------------------------------------------------------------
DATA_BLOCK_SIZE = 1 << 20  # 1 MiB — smallest value validate_master_block() accepts
TOTAL_DATA_BLOCKS = 8
VIDEO_AREA_OFFSET = 0x100000
LOG_OFFSET = 0x1000
LOG_SIZE = 0x1000
BACKUP_MASTER_OFFSET = 0x2000
HIKBTREE_OFFSET = VIDEO_AREA_OFFSET + DATA_BLOCK_SIZE * TOTAL_DATA_BLOCKS
HIKBTREE_HEADER_SIZE = PAGE_SIZE
FIRST_PAGE_OFFSET = HIKBTREE_OFFSET + HIKBTREE_HEADER_SIZE
IMAGE_SIZE = FIRST_PAGE_OFFSET + PAGE_SIZE * 2

ALLOC_ALLOCATED = 0x0000000000000000
ALLOC_CLEARED = 0xFFFFFFFFFFFFFFFF  # docs/reference/hikvision_fs.md §6.4

INIT_TIME = 1_700_000_000  # 2023-11-14T22:13:20Z
FIRMWARE = b"V4.30.005"

# Payload written per data block, well under DATA_BLOCK_SIZE so the IDR table has room.
PAYLOAD_TARGET_BYTES = 96 * 1024


@dataclass(frozen=True)
class PlannedRecording:
    """One recording the builder writes, and the ground truth the tests assert against."""

    channel: int
    block_index: int
    start_unix: int
    duration_s: int
    event_type: str  # "continuous" | "event"
    allocation_state: str
    idr_count: int = 6

    @property
    def end_unix(self) -> int:
        return self.start_unix + self.duration_s

    @property
    def data_offset(self) -> int:
        return VIDEO_AREA_OFFSET + self.block_index * DATA_BLOCK_SIZE

    def idr_timestamps(self) -> list[int]:
        """IDR cadence: spanning the window for continuous, a short burst for event."""
        if self.event_type == "continuous":
            span = int(self.duration_s * 0.95)
        else:
            span = max(1, int(self.duration_s * 0.1))
        step = span / max(1, self.idr_count - 1)
        base = self.start_unix + (10 if self.event_type == "event" else 0)
        return [base + int(round(index * step)) for index in range(self.idr_count)]


# Ground-truth plan. Six recordings across two channels: continuous + event on each,
# one deleted (index entry cleared), one still recording. Plus an unused index slot
# that must NOT be reported as a recording.
PLAN: tuple[PlannedRecording, ...] = (
    PlannedRecording(channel=1, block_index=0, start_unix=INIT_TIME + 3600, duration_s=300,
                     event_type="continuous", allocation_state="allocated"),
    PlannedRecording(channel=1, block_index=1, start_unix=INIT_TIME + 7200, duration_s=300,
                     event_type="event", allocation_state="allocated"),
    PlannedRecording(channel=2, block_index=2, start_unix=INIT_TIME + 3600, duration_s=300,
                     event_type="continuous", allocation_state="allocated"),
    PlannedRecording(channel=2, block_index=3, start_unix=INIT_TIME + 7200, duration_s=300,
                     event_type="event", allocation_state="allocated"),
    PlannedRecording(channel=1, block_index=4, start_unix=INIT_TIME + 1800, duration_s=300,
                     event_type="continuous", allocation_state="deleted (index entry cleared)"),
    PlannedRecording(channel=2, block_index=5, start_unix=INIT_TIME + 10800, duration_s=300,
                     event_type="continuous", allocation_state="recording"),
)

EXPECTED_RECORDING_COUNT = len(PLAN)
EXPECTED_DELETED_COUNT = sum(1 for item in PLAN if item.allocation_state.startswith("deleted"))


@dataclass
class BuiltImage:
    path: Path
    plan: tuple[PlannedRecording, ...]
    provenance: str = "emulated"
    sources: tuple[str, ...] = field(
        default=(
            "layout: Han, Jeong & Lee, ICDF2C 2015 (docs/reference/hikvision_fs.md)",
            "video payload: CAVIAR Walk1, CC BY-SA, EC IST 2001 37540",
        )
    )

    @property
    def expected_count(self) -> int:
        return len(self.plan)

    @property
    def expected_deleted(self) -> int:
        return sum(1 for item in self.plan if item.allocation_state.startswith("deleted"))


# --------------------------------------------------------------------------------------
# Structure writers
# --------------------------------------------------------------------------------------


def _write_master_sector(disk: bytearray, offset: int) -> None:
    """docs/reference/hikvision_fs.md §3."""
    block = bytearray(0x100)
    block[MASTER_SIG_OFF : MASTER_SIG_OFF + len(HIKVISION_SIG)] = HIKVISION_SIG
    block[MASTER_VERSION_OFF : MASTER_VERSION_OFF + len(FIRMWARE)] = FIRMWARE
    struct.pack_into("<Q", block, MASTER_CAPACITY_OFF, IMAGE_SIZE)
    struct.pack_into("<Q", block, MASTER_LOG_OFF, LOG_OFFSET)
    struct.pack_into("<Q", block, MASTER_LOG_SIZE_OFF, LOG_SIZE)
    struct.pack_into("<Q", block, MASTER_VIDEO_AREA_OFF, VIDEO_AREA_OFFSET)
    struct.pack_into("<Q", block, MASTER_DATA_BLOCK_SIZE_OFF, DATA_BLOCK_SIZE)
    struct.pack_into("<I", block, MASTER_TOTAL_BLOCKS_OFF, TOTAL_DATA_BLOCKS)
    struct.pack_into("<Q", block, MASTER_HIKBTREE_OFF, HIKBTREE_OFFSET)
    struct.pack_into("<I", block, MASTER_HIKBTREE_SIZE_OFF, HIKBTREE_HEADER_SIZE + PAGE_SIZE)
    struct.pack_into("<Q", block, MASTER_HIKBTREE2_OFF, 0)
    struct.pack_into("<I", block, MASTER_HIKBTREE2_SIZE_OFF, 0)
    struct.pack_into("<I", block, MASTER_INIT_TIME_OFF, INIT_TIME)
    disk[offset : offset + len(block)] = block


def _write_system_logs(disk: bytearray) -> None:
    """RATS records — docs/reference/hikvision_fs.md §4.

    Only the signature and created time are written. We deliberately do not invent a field
    layout for the type byte or description, because we cannot cite one.
    """
    cursor = LOG_OFFSET
    for index, recording in enumerate(PLAN):
        record = bytearray(64)
        record[0:8] = b"RATS\x01\x00\x00\x00"
        struct.pack_into("<I", record, 8, recording.start_unix)
        disk[cursor : cursor + len(record)] = record
        cursor += len(record)
        if cursor + 64 > LOG_OFFSET + LOG_SIZE:
            break
        _ = index


def _picture_indexed_payload(target_bytes: int) -> bytes:
    """Real H.264 NALs, each preceded by a Hikvision picture-index header.

    docs/reference/hikvision_fs.md §5.1: the recorder writes ``00 00 01 BA`` plus a picture
    index in front of each NAL unit. This is what makes the stream unreadable to third-party
    players and is exactly what our unwrap path has to strip.
    """
    source = get_nal_source()
    out = bytearray()
    picture_index = 1
    guard = 0
    while len(out) < target_bytes and guard < 4096:
        guard += 1
        for nal in split_annexb_nals(source.next_gop()):
            if not nal:
                continue
            out += PICTURE_INDEX_BA
            # High nibble set so the index can never itself form a NAL start code.
            out += struct.pack("<I", 0x10000000 | (picture_index & 0xFFFFFF))
            picture_index += 1
            if nal.startswith(b"\x00\x00\x00\x01"):
                out += nal
            elif nal.startswith(b"\x00\x00\x01"):
                out += b"\x00" + nal
            else:
                out += b"\x00\x00\x00\x01" + nal
            if len(out) >= target_bytes:
                break
    return bytes(out)


def _write_idr_table(disk: bytearray, block_start: int, timestamps: list[int]) -> None:
    """Fixed 56-byte ``OFNI`` records at the tail of the data block — §5.2.

    Written contiguously so the table reads forward from its lowest record, which is how the
    parser walks it. Layout inside the record is deliberately minimal: signature, picture
    index, timestamp. The parser does not depend on those positions — it scans the record for
    a plausible recorder time — precisely because the real layout is not published.
    """
    block_end = block_start + DATA_BLOCK_SIZE
    table_start = block_end - len(timestamps) * IDR_RECORD_SIZE
    for index, timestamp in enumerate(timestamps):
        record = bytearray(IDR_RECORD_SIZE)
        record[0:4] = IDR_TABLE_SIG
        struct.pack_into("<I", record, 4, index)
        struct.pack_into("<I", record, 8, timestamp)
        at = table_start + index * IDR_RECORD_SIZE
        disk[at : at + IDR_RECORD_SIZE] = record


def _entry_bytes(recording: PlannedRecording) -> bytes:
    """One 48-byte data block entry — docs/reference/hikvision_fs.md §6.3, §6.4, §6.5."""
    entry = bytearray(ENTRY_SIZE)
    state = recording.allocation_state
    if state == "allocated":
        flag, start, end = ALLOC_ALLOCATED, recording.start_unix, recording.end_unix
    elif state == "recording":
        # §6.5: an in-progress recording keeps the allocated flag and the sentinel time.
        flag, start, end = ALLOC_ALLOCATED, TIME_SENTINEL, 0
    elif state.startswith("deleted"):
        # §7: initialization clears the index flag; the timestamps and the data pointer are
        # left behind, and the footage is still on the platter.
        flag, start, end = ALLOC_CLEARED, recording.start_unix, recording.end_unix
    else:
        raise ValueError(f"unsupported planned allocation state: {state}")

    struct.pack_into("<Q", entry, ENTRY_ALLOC_FLAG_OFF, flag)
    entry[ENTRY_CHANNEL_OFF] = recording.channel & 0xFF
    struct.pack_into("<I", entry, ENTRY_START_TS_OFF, start)
    struct.pack_into("<I", entry, ENTRY_END_TS_OFF, end)
    struct.pack_into("<Q", entry, ENTRY_DATA_OFFSET_OFF, recording.data_offset)
    return bytes(entry)


def _unused_entry_bytes() -> bytes:
    """A slot the recorder has never written: flag cleared, no data pointer."""
    entry = bytearray(ENTRY_SIZE)
    struct.pack_into("<Q", entry, ENTRY_ALLOC_FLAG_OFF, ALLOC_CLEARED)
    struct.pack_into("<I", entry, ENTRY_START_TS_OFF, TIME_SENTINEL)
    return bytes(entry)


def _write_hikbtree(disk: bytearray) -> None:
    """docs/reference/hikvision_fs.md §6."""
    header = bytearray(HIKBTREE_HEADER_SIZE)
    header[TREE_SIG_OFF : TREE_SIG_OFF + len(HIKBTREE_SIG)] = HIKBTREE_SIG
    struct.pack_into("<Q", header, TREE_FIRST_PAGE_OFF, FIRST_PAGE_OFFSET)
    disk[HIKBTREE_OFFSET : HIKBTREE_OFFSET + len(header)] = header

    page = bytearray(PAGE_SIZE)
    entries = [_entry_bytes(item) for item in PLAN] + [_unused_entry_bytes()]
    struct.pack_into("<I", page, PAGE_ENTRY_COUNT_OFF, len(entries))
    struct.pack_into("<Q", page, PAGE_NEXT_PAGE_OFF, 0xFFFFFFFFFFFFFFFF)
    for index, entry in enumerate(entries):
        at = PAGE_ENTRY_BASE + index * ENTRY_SIZE
        page[at : at + ENTRY_SIZE] = entry
    disk[FIRST_PAGE_OFFSET : FIRST_PAGE_OFFSET + PAGE_SIZE] = page


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def build_emulated_bytes() -> bytes:
    """Assemble the full emulated Hikvision disk image in memory."""
    get_nal_source().reset()
    disk = bytearray(IMAGE_SIZE)
    disk[0 : len(EMULATION_STAMP)] = EMULATION_STAMP

    _write_master_sector(disk, MASTER_BLOCK_OFFSET)
    _write_master_sector(disk, BACKUP_MASTER_OFFSET)
    _write_system_logs(disk)

    payload = _picture_indexed_payload(PAYLOAD_TARGET_BYTES)
    for recording in PLAN:
        start = recording.data_offset
        disk[start : start + len(payload)] = payload
        _write_idr_table(disk, start, recording.idr_timestamps())

    _write_hikbtree(disk)
    return bytes(disk)


def build_emulated_image(dest: Path) -> BuiltImage:
    """Write the emulated image to ``dest`` and return it with its ground-truth plan."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_emulated_bytes())
    return BuiltImage(path=dest, plan=PLAN)
