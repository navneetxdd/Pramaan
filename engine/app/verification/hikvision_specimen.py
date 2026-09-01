from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.app.parsers.schemas.hikvision_fs import (
    MASTER_BLOCK_OFFSET,
    HikbtreeEntry,
    build_hikbtree_header,
    build_hikbtree_page,
    build_master_block,
    wrap_mpegps,
)
from engine.app.verification.media_fixture import get_nal_source

_LAB_EPOCH = 1_700_000_000
DISK_SIZE = 4 * 1024 * 1024

HIKBTREE_OFFSET = 0x1000
PAGE_OFFSET = 0x1800
DATA_BASE = 0x100000


def build_hikvision_lab_specimen() -> bytes:
    """Synthetic Hikvision disk: master @ 0x200, HIKBTREE index, MPEG-PS data blocks."""
    get_nal_source().reset()
    disk = bytearray(DISK_SIZE)

    entries: list[HikbtreeEntry] = []
    data_cursor = DATA_BASE
    frame_index = 0
    for channel in (1, 1, 2, 1):
        access_unit = get_nal_source().next_decodable_access_unit(min_len=64)
        ps_blob = wrap_mpegps(access_unit)
        disk[data_cursor : data_cursor + len(ps_blob)] = ps_blob
        start = _LAB_EPOCH + frame_index * 60
        entries.append(
            HikbtreeEntry(
                channel=channel,
                start_unix=start,
                end_unix=start + 30,
                data_offset=data_cursor,
                has_footage=True,
                stale=False,
            )
        )
        data_cursor += max(len(ps_blob), 0x10000)
        frame_index += 1

    # Stale / deleted-recording tell
    entries.append(
        HikbtreeEntry(
            channel=2,
            start_unix=_LAB_EPOCH + 900,
            end_unix=_LAB_EPOCH + 930,
            data_offset=DATA_BASE + 0x80000,
            has_footage=False,
            stale=True,
        )
    )

    disk[HIKBTREE_OFFSET : HIKBTREE_OFFSET + len(build_hikbtree_header(PAGE_OFFSET))] = build_hikbtree_header(
        PAGE_OFFSET
    )
    page = build_hikbtree_page(entries)
    disk[PAGE_OFFSET : PAGE_OFFSET + len(page)] = page

    master = build_master_block(
        hikbtree_offset=HIKBTREE_OFFSET,
        hikbtree_size=len(build_hikbtree_header(PAGE_OFFSET)),
        init_time=_LAB_EPOCH,
        video_area_offset=DATA_BASE,
    )
    disk[MASTER_BLOCK_OFFSET : MASTER_BLOCK_OFFSET + len(master)] = master
    disk[512:512 + len(b"HIKVISION-DVR\x00")] = b"HIKVISION-DVR\x00"
    return bytes(disk)


def write_hikvision_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_hikvision_lab_specimen())
    return dest
