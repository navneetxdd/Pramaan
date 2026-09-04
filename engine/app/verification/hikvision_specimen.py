"""Hikvision lab specimen — FABRICATED EVIDENCE, not a real acquisition.

Scheduled for deletion together with the ``/devices/acquire/synthetic`` route (that removal is
owned by the Identification/Settings workstream, not by this module). It is kept alive here
only so that route keeps working until it is removed.

It previously imported ``build_master_block`` / ``build_hikbtree_page`` from the engine's
Hikvision schema module. Those builders have been removed from the engine: a parser that can
only be tested against structures it wrote itself proves nothing. The equivalent structures are
written inline below, from the documented offsets in ``docs/reference/hikvision_fs.md``, and
the parser is validated for real against the emulated image in
``engine/tests/support/hikvision_builder.py``.
"""

from __future__ import annotations

import struct
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
    MASTER_HIKBTREE_OFF,
    MASTER_HIKBTREE_SIZE_OFF,
    MASTER_INIT_TIME_OFF,
    MASTER_SIG_OFF,
    MASTER_TOTAL_BLOCKS_OFF,
    MASTER_VERSION_OFF,
    MASTER_VIDEO_AREA_OFF,
    PAGE_ENTRY_BASE,
    PAGE_ENTRY_COUNT_OFF,
    PAGE_NEXT_PAGE_OFF,
    PAGE_SIZE,
    PICTURE_INDEX_BA,
    TREE_FIRST_PAGE_OFF,
    TREE_SIG_OFF,
)
from engine.app.verification.media_fixture import get_nal_source, split_annexb_nals

SPECIMEN_LABEL = b"PRAMAAN-LAB-SPECIMEN-HIKVISION"

_LAB_EPOCH = 1_700_000_000
DATA_BLOCK_SIZE = 1 << 20
TOTAL_DATA_BLOCKS = 6
VIDEO_AREA_OFFSET = 0x100000
HIKBTREE_OFFSET = VIDEO_AREA_OFFSET + DATA_BLOCK_SIZE * TOTAL_DATA_BLOCKS
FIRST_PAGE_OFFSET = HIKBTREE_OFFSET + PAGE_SIZE

# Deliberately small so the entries below span a chain of index pages rather than
# fitting on one. A real 4 KB page holds 84 entries, which a fixture this size would
# never reach — leaving the parser's page-walk, and any bug in it, unexercised on the
# one image the app actually acquires.
ENTRIES_PER_PAGE = 3
INDEX_PAGE_COUNT = 4
DISK_SIZE = FIRST_PAGE_OFFSET + PAGE_SIZE * INDEX_PAGE_COUNT

_ALLOC_ALLOCATED = 0x0000000000000000
_ALLOC_CLEARED = 0xFFFFFFFFFFFFFFFF

# (channel, block index, allocated?, overwritten_by_seconds)
#
# The final entry is deliberately partially overwritten: its IDR table retains a record
# from an hour before the entry's own start time, which is the published tell for a
# block reused by a later recording ([HAN2015] §3.3). It must come back PARTIAL.
_LAYOUT = (
    (1, 0, True, 0),
    (1, 1, True, 0),
    (2, 2, True, 0),
    (1, 3, True, 0),
    (2, 4, False, 0),
    (2, 5, True, 3600),
)


def _picture_indexed_payload(target_bytes: int) -> bytes:
    """Real H.264 NALs behind Hikvision picture-index headers (see reference doc §5.1)."""
    source = get_nal_source()
    out = bytearray()
    index = 1
    guard = 0
    while len(out) < target_bytes and guard < 1024:
        guard += 1
        for nal in split_annexb_nals(source.next_gop()):
            if not nal:
                continue
            out += PICTURE_INDEX_BA + struct.pack("<I", 0x10000000 | (index & 0xFFFFFF))
            index += 1
            if nal.startswith(b"\x00\x00\x00\x01"):
                out += nal
            elif nal.startswith(b"\x00\x00\x01"):
                out += b"\x00" + nal
            else:
                out += b"\x00\x00\x00\x01" + nal
            if len(out) >= target_bytes:
                break
    return bytes(out)


def build_hikvision_lab_specimen() -> bytes:
    """Fabricated Hikvision disk: master sector, HIKBTREE index, H.264 data blocks."""
    get_nal_source().reset()
    disk = bytearray(DISK_SIZE)
    disk[0 : len(SPECIMEN_LABEL)] = SPECIMEN_LABEL

    master = bytearray(0x100)
    master[MASTER_SIG_OFF : MASTER_SIG_OFF + len(HIKVISION_SIG)] = HIKVISION_SIG
    master[MASTER_VERSION_OFF : MASTER_VERSION_OFF + 9] = b"V4.30.005"
    struct.pack_into("<Q", master, MASTER_CAPACITY_OFF, DISK_SIZE)
    struct.pack_into("<Q", master, MASTER_VIDEO_AREA_OFF, VIDEO_AREA_OFFSET)
    struct.pack_into("<Q", master, MASTER_DATA_BLOCK_SIZE_OFF, DATA_BLOCK_SIZE)
    struct.pack_into("<I", master, MASTER_TOTAL_BLOCKS_OFF, TOTAL_DATA_BLOCKS)
    struct.pack_into("<Q", master, MASTER_HIKBTREE_OFF, HIKBTREE_OFFSET)
    struct.pack_into("<I", master, MASTER_HIKBTREE_SIZE_OFF, PAGE_SIZE * INDEX_PAGE_COUNT)
    struct.pack_into("<I", master, MASTER_INIT_TIME_OFF, _LAB_EPOCH)
    disk[MASTER_BLOCK_OFFSET : MASTER_BLOCK_OFFSET + len(master)] = master

    payload = _picture_indexed_payload(64 * 1024)
    entries: list[bytes] = []

    for slot, (channel, block_index, allocated, overwritten_by) in enumerate(_LAYOUT):
        block_start = VIDEO_AREA_OFFSET + block_index * DATA_BLOCK_SIZE
        disk[block_start : block_start + len(payload)] = payload

        start = _LAB_EPOCH + 3600 + slot * 600
        end = start + 300
        stamps = [start + step * 60 for step in range(5)]
        if overwritten_by:
            # A surviving record from the recording this block partly overwrote.
            stamps.insert(0, start - overwritten_by)
        table_start = block_start + DATA_BLOCK_SIZE - len(stamps) * IDR_RECORD_SIZE
        for idr_index, stamp in enumerate(stamps):
            record = bytearray(IDR_RECORD_SIZE)
            record[0:4] = IDR_TABLE_SIG
            struct.pack_into("<I", record, 4, idr_index)
            struct.pack_into("<I", record, 8, stamp)
            at = table_start + idr_index * IDR_RECORD_SIZE
            disk[at : at + IDR_RECORD_SIZE] = record

        entry = bytearray(ENTRY_SIZE)
        struct.pack_into("<Q", entry, ENTRY_ALLOC_FLAG_OFF, _ALLOC_ALLOCATED if allocated else _ALLOC_CLEARED)
        entry[ENTRY_CHANNEL_OFF] = channel
        struct.pack_into("<I", entry, ENTRY_START_TS_OFF, start)
        struct.pack_into("<I", entry, ENTRY_END_TS_OFF, end)
        struct.pack_into("<Q", entry, ENTRY_DATA_OFFSET_OFF, block_start)
        entries.append(bytes(entry))

    header = bytearray(PAGE_SIZE)
    header[TREE_SIG_OFF : TREE_SIG_OFF + len(HIKBTREE_SIG)] = HIKBTREE_SIG
    struct.pack_into("<Q", header, TREE_FIRST_PAGE_OFF, FIRST_PAGE_OFFSET)
    disk[HIKBTREE_OFFSET : HIKBTREE_OFFSET + PAGE_SIZE] = header

    # Chain the entries across a page list so the walk is genuinely exercised.
    chunks = [
        entries[i : i + ENTRIES_PER_PAGE]
        for i in range(0, len(entries), ENTRIES_PER_PAGE)
    ]
    for page_index, chunk in enumerate(chunks):
        page_offset = FIRST_PAGE_OFFSET + page_index * PAGE_SIZE
        is_last = page_index == len(chunks) - 1
        page = bytearray(PAGE_SIZE)
        struct.pack_into("<I", page, PAGE_ENTRY_COUNT_OFF, len(chunk))
        struct.pack_into(
            "<Q",
            page,
            PAGE_NEXT_PAGE_OFF,
            0xFFFFFFFFFFFFFFFF if is_last else page_offset + PAGE_SIZE,
        )
        for slot, entry in enumerate(chunk):
            at = PAGE_ENTRY_BASE + slot * ENTRY_SIZE
            page[at : at + ENTRY_SIZE] = entry
        disk[page_offset : page_offset + PAGE_SIZE] = page
    return bytes(disk)


def write_hikvision_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_hikvision_lab_specimen())
    return dest
