from __future__ import annotations

import struct
from pathlib import Path

from engine.app.parsers.schemas.honeywell import (
    CHANNEL_DELIMITER,
    HoneywellBlockGroupIndex,
    HoneywellChannelEntry,
    HoneywellNalHeader,
    HoneywellPartitionHeader,
    NAL_START_4,
    SECTOR_SIZE,
    rounded_frame_length_u16,
)

SECTOR_34_OFFSET = 34 * SECTOR_SIZE
PARTITION_BASE = 0x10000
CHANNEL_LIST_BASE = PARTITION_BASE + 0x400000
VIDEO_DATA_BASE = 0x200000


def _gpt_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    sector[0:8] = b"EFI PART"
    sector[8:12] = struct.pack("<I", 92)
    sector[72:80] = struct.pack("<Q", 2)
    return bytes(sector)


def _machine_data_sector() -> bytes:
    sector = bytearray(SECTOR_SIZE)
    label = b"Honeywell HWDVR-Lab-Specimen\x00"
    sector[: len(label)] = label
    return bytes(sector)


def _build_nal_frame(*, frame_type: int, timestamp_us: int, payload_extra: int = 64) -> bytes:
    nal_type_byte = 0x65 if frame_type == 0x82 else 0x41
    payload = NAL_START_4 + bytes([nal_type_byte]) + (b"\x00" * payload_extra)
    header = HoneywellNalHeader.build(
        {
            "frame_type": frame_type,
            "width_height": 0x078002D0,
            "nal_length": len(payload),
            "timestamp_us": timestamp_us,
        }
    )
    return header + payload


def build_honeywell_lab_specimen() -> bytes:
    """Synthetic Honeywell GPT disk with both deletion-recovery mechanisms."""
    header_start_time = 1_700_000_000
    deleted_ts = header_start_time - 3600
    active_ts = header_start_time + 120

    frames = [
        (1, active_ts, 0x82),
        (1, deleted_ts, 0x02),
        (2, active_ts + 30, 0x82),
    ]
    video_parts: list[bytes] = []
    frame_offsets: list[tuple[int, int, int, int]] = []
    cursor = VIDEO_DATA_BASE
    for channel, ts, ftype in frames:
        frame_offsets.append((channel, ts, cursor, ftype))
        frame = _build_nal_frame(frame_type=ftype, timestamp_us=ts * 1_000_000)
        video_parts.append(frame)
        video_parts.append(CHANNEL_DELIMITER)
        cursor += len(frame) + len(CHANNEL_DELIMITER)

    orphan_ts = deleted_ts - 600
    orphan = _build_nal_frame(frame_type=0x82, timestamp_us=orphan_ts * 1_000_000)
    video_parts.append(b"\x00" * 4096)
    video_parts.append(orphan)
    video_end = VIDEO_DATA_BASE + sum(len(p) for p in video_parts)

    size = max(video_end + 4096, CHANNEL_LIST_BASE + 64)
    blob = bytearray(size)

    blob[SECTOR_SIZE : SECTOR_SIZE * 2] = _gpt_sector()
    blob[SECTOR_34_OFFSET : SECTOR_34_OFFSET + SECTOR_SIZE] = _machine_data_sector()

    part_header = HoneywellPartitionHeader.build(
        {
            "video_data_start": VIDEO_DATA_BASE,
            "next_write_offset": video_end,
            "available_memory": 512 * 1024 * 1024,
            "total_allocatable": 512 * 1024 * 1024,
            "header_pad": b"\x00" * 32,
        }
    )
    blob[PARTITION_BASE : PARTITION_BASE + len(part_header)] = part_header

    group = HoneywellBlockGroupIndex.build(
        {"reserved": b"\x00" * 4, "start_timestamp": header_start_time, "pad": b"\x00" * 8}
    )
    blob[PARTITION_BASE + 0x40 : PARTITION_BASE + 0x40 + len(group)] = group

    for index, (channel, ts, offset, _ftype) in enumerate(frame_offsets):
        entry = HoneywellChannelEntry.build(
            {
                "channel_id": channel,
                "stream_type": 0x00,
                "frame_length_rounded": rounded_frame_length_u16(512),
                "frame_start_time": ts,
                "frame_start_offset": offset,
                "reserved": b"\x00" * 4,
            }
        )
        off = CHANNEL_LIST_BASE + index * 16
        blob[off : off + 16] = entry

    cursor = VIDEO_DATA_BASE
    for part in video_parts:
        blob[cursor : cursor + len(part)] = part
        cursor += len(part)

    return bytes(blob)


def write_honeywell_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_honeywell_lab_specimen())
    return dest
