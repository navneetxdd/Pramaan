from __future__ import annotations

import struct
from dataclasses import dataclass

from construct import Bytes, Const, Int16ul, Int32ul, Int64ul, Int8ul, Struct

SECTOR_SIZE = 512
SECTOR_34 = 34
MACHINE_DATA_OFFSET = SECTOR_34 * SECTOR_SIZE
GPT_SIGNATURE = b"EFI PART"
HONEYWELL_HINT = b"Honeywell"

PARTITION_HEADER_OFFSET = 0x0000
VIDEO_BLOCK_LIST_OFFSET = 0x40000
VIDEO_CHANNEL_LIST_OFFSET = 0x400000
VIDEO_DATA_REGION_OFFSET = 0x80000000

HoneywellPartitionHeader = Struct(
    "video_data_start" / Int64ul,
    "next_write_offset" / Int64ul,
    "available_memory" / Int64ul,
    "total_allocatable" / Int64ul,
    "header_pad" / Bytes(32),
)

HoneywellBlockGroupIndex = Struct(
    "reserved" / Bytes(4),
    "start_timestamp" / Int32ul,
    "pad" / Bytes(8),
)

HoneywellChannelEntry = Struct(
    "channel_id" / Int8ul,
    "stream_type" / Int8ul,
    "frame_length_rounded" / Int16ul,
    "frame_start_time" / Int32ul,
    "frame_start_offset" / Int32ul,
    "reserved" / Bytes(4),
)

HoneywellNalHeader = Struct(
    "frame_type" / Int8ul,
    "marker" / Const(b"\x80\x01\x00"),
    "width_height" / Int32ul,
    "nal_length" / Int32ul,
    "timestamp_us" / Int64ul,
)

NAL_START_4 = b"\x00\x00\x00\x01"
CHANNEL_DELIMITER = b"\x00" * 20
FRAME_TYPES = {0x82, 0x02}


@dataclass(frozen=True)
class HoneywellPartitionInfo:
    partition_base: int
    video_data_start: int
    header_start_time: int
    machine_data_found: bool


def detect_honeywell_layout(data: bytes) -> HoneywellPartitionInfo | None:
    machine = HONEYWELL_HINT in data[: min(len(data), 512 * 512)]
    has_gpt = GPT_SIGNATURE in data[: min(len(data), 512 * 512)]
    if not machine and not has_gpt:
        return None

    partition_base = 0x10000 if len(data) > 0x10000 else 0
    if partition_base + 0x40 > len(data):
        return None

    header = HoneywellPartitionHeader.parse(data[partition_base : partition_base + 0x40])
    video_start = int(header.video_data_start)
    if video_start <= 0 or video_start >= len(data):
        video_start = min(len(data) - 256, VIDEO_DATA_REGION_OFFSET)
        if video_start <= partition_base:
            video_start = partition_base + 0x200000

    header_start_time = 0
    idx_off = partition_base + 0x40
    if idx_off + 16 <= len(data):
        group = HoneywellBlockGroupIndex.parse(data[idx_off : idx_off + 16])
        header_start_time = int(group.start_timestamp)

    return HoneywellPartitionInfo(
        partition_base=partition_base,
        video_data_start=video_start,
        header_start_time=header_start_time,
        machine_data_found=machine,
    )


def parse_channel_entry(data: bytes, offset: int) -> tuple[dict, bool]:
    if offset + 16 > len(data):
        return {}, False
    raw = data[offset : offset + 16]
    if raw == b"\x00" * 16:
        return {}, False
    entry = HoneywellChannelEntry.parse(raw)
    if entry.channel_id == 0 and entry.frame_start_time == 0:
        return {}, False
    return entry, True


def frame_length_bytes(rounded: int) -> int:
    return int(rounded) * 4096


def validate_nal_header(data: bytes, offset: int) -> tuple[int, dict] | None:
    if offset + 20 > len(data):
        return None
    if data[offset] not in FRAME_TYPES:
        return None
    if data[offset + 1 : offset + 4] != b"\x80\x01\x00":
        return None
    try:
        parsed = HoneywellNalHeader.parse(data[offset : offset + 20])
    except Exception:
        return None
    total = 20 + 6 + int(parsed.nal_length)
    if offset + total > len(data):
        return None
    if data[offset + 20 : offset + 26] != NAL_START_4 + bytes([parsed.frame_type]):
        if NAL_START_4 not in data[offset + 20 : offset + 26]:
            return None
    return total, parsed


def rounded_frame_length_u16(byte_len: int) -> int:
    return max(1, (byte_len + 4095) // 4096)
