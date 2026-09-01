from __future__ import annotations

import struct
from dataclasses import dataclass

MASTER_BLOCK_OFFSET = 0x200
HIKVISION_SIG = b"HIKVISION@HANGZHOU"
HIKBTREE_SIG = b"HIKBTREE"
MPEG_PS_PACK = b"\x00\x00\x01\xba"
ENTRY_SIZE = 48


@dataclass(frozen=True)
class HikbtreeEntry:
    channel: int
    start_unix: int
    end_unix: int
    data_offset: int
    has_footage: bool
    stale: bool


def wrap_mpegps(h264_es: bytes) -> bytes:
    """Minimal MPEG-PS pack + video PES wrapping Annex-B H.264 elementary stream."""
    pack = MPEG_PS_PACK + bytes([0x44, 0x00, 0x04, 0x00, 0x04, 0x01, 0x01, 0x89, 0xC3])
    pes = b"\x00\x00\x01\xe0"
    pes_header = b"\x80\x80\x05\x00\x00\x00\x00\x00"
    payload = h264_es
    pes_len = len(pes_header) + len(payload)
    if pes_len > 0xFFFF:
        pes_len = 0
    pes += struct.pack(">H", pes_len)
    pes += pes_header
    return pack + pes + payload


def carve_mpegps_block(data: bytes) -> list[bytes]:
    runs: list[bytes] = []
    start = 0
    hits = [idx for idx in range(len(data) - 3) if data[idx : idx + 4] == MPEG_PS_PACK]
    if not hits:
        return [data] if data else []
    for index, hit in enumerate(hits):
        end = hits[index + 1] if index + 1 < len(hits) else len(data)
        if end > hit:
            runs.append(data[hit:end])
    return runs


def parse_master_block(data: bytes, offset: int = MASTER_BLOCK_OFFSET) -> dict | None:
    if offset + 0xF4 > len(data):
        return None
    if data[offset + 0x10 : offset + 0x10 + len(HIKVISION_SIG)] != HIKVISION_SIG:
        return None
    return {
        "hikbtree_offset": struct.unpack_from("<Q", data, offset + 0x98)[0],
        "hikbtree_size": struct.unpack_from("<I", data, offset + 0xA0)[0],
        "video_area_offset": struct.unpack_from("<Q", data, offset + 0x78)[0],
        "init_time": struct.unpack_from("<I", data, offset + 0xF0)[0],
    }


def parse_hikbtree_entries(data: bytes, tree_offset: int) -> list[HikbtreeEntry]:
    if tree_offset + 0x60 > len(data):
        return []
    if data[tree_offset + 0x10 : tree_offset + 0x18] != HIKBTREE_SIG:
        return []
    page_offset = struct.unpack_from("<Q", data, tree_offset + 0x58)[0]
    entries: list[HikbtreeEntry] = []
    while page_offset and page_offset < len(data):
        count = struct.unpack_from("<I", data, page_offset + 0x10)[0]
        next_page = struct.unpack_from("<Q", data, page_offset + 0x20)[0]
        entry_base = page_offset + 0x60
        for index in range(min(count, 64)):
            base = entry_base + index * ENTRY_SIZE
            if base + ENTRY_SIZE > len(data):
                break
            flag = struct.unpack_from("<Q", data, base + 0x08)[0]
            channel = data[base + 0x11]
            start_unix = struct.unpack_from("<I", data, base + 0x18)[0]
            end_unix = struct.unpack_from("<I", data, base + 0x1C)[0]
            data_offset = struct.unpack_from("<Q", data, base + 0x20)[0]
            has_footage = flag == 0
            stale = flag != 0 and data_offset > 0
            if has_footage or stale:
                entries.append(
                    HikbtreeEntry(
                        channel=channel,
                        start_unix=start_unix,
                        end_unix=end_unix,
                        data_offset=data_offset,
                        has_footage=has_footage,
                        stale=stale,
                    )
                )
        if next_page in {0, 0xFFFFFFFFFFFFFFFF}:
            break
        page_offset = next_page
    return entries


def build_master_block(
    *,
    hikbtree_offset: int,
    hikbtree_size: int,
    init_time: int,
    video_area_offset: int,
    data_block_size: int = 256 * 1024,
) -> bytes:
    block = bytearray(512)
    block[0x10 : 0x10 + len(HIKVISION_SIG)] = HIKVISION_SIG
    block[0x30 : 0x30 + 14] = b"V5.00.0000000"
    struct.pack_into("<Q", block, 0x78, video_area_offset)
    struct.pack_into("<Q", block, 0x88, data_block_size)
    struct.pack_into("<I", block, 0x90, 4)
    struct.pack_into("<Q", block, 0x98, hikbtree_offset)
    struct.pack_into("<I", block, 0xA0, hikbtree_size)
    struct.pack_into("<I", block, 0xF0, init_time)
    return bytes(block)


def build_hikbtree_page(entries: list[HikbtreeEntry], *, next_page: int = 0xFFFFFFFFFFFFFFFF) -> bytes:
    page = bytearray(0x800)
    struct.pack_into("<I", page, 0x10, len(entries))
    struct.pack_into("<Q", page, 0x20, next_page)
    for index, entry in enumerate(entries):
        base = 0x60 + index * ENTRY_SIZE
        flag = 0 if entry.has_footage else 1
        struct.pack_into("<Q", page, base + 0x08, flag)
        page[base + 0x11] = entry.channel & 0xFF
        struct.pack_into("<I", page, base + 0x18, entry.start_unix)
        struct.pack_into("<I", page, base + 0x1C, entry.end_unix)
        struct.pack_into("<Q", page, base + 0x20, entry.data_offset)
    return bytes(page)


def build_hikbtree_header(first_page_offset: int) -> bytes:
    header = bytearray(0x100)
    header[0x10 : 0x18] = HIKBTREE_SIG
    struct.pack_into("<Q", header, 0x58, first_page_offset)
    return bytes(header)
