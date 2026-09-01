from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.app.parsers.schemas.dhav import (
    DHAV_TYPE_I,
    DHAV_TYPE_P,
    build_h264_ext_tlvs,
    seal_dhav_video_frame,
)
from engine.app.verification.media_fixture import NalPayloadSource

_LAB_EPOCH = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
_nal_source = NalPayloadSource()


def _frame_time(index: int) -> datetime:
    return _LAB_EPOCH.replace(second=min(59, 20 + index % 40))


def _video_frame(frame_type: int, channel: int, frame_number: int, index: int) -> bytes:
    if frame_type == DHAV_TYPE_I:
        payload = _nal_source.next_decodable_access_unit(min_len=64)
    else:
        payload = _nal_source.next_single_nal()
    return seal_dhav_video_frame(
        frame_type=frame_type,
        channel=channel,
        frame_number=frame_number,
        when=_frame_time(index),
        payload=payload,
        ext=build_h264_ext_tlvs(),
    )


def build_dahua_lab_specimen() -> bytes:
    """
    Synthetic DHAV stream aligned with libavformat/dhav.c.
    Starts with DAHUA 0x400 header block containing DHFS4.1 marker for detection.
    """
    _nal_source.reset()
    header_block = bytearray(0x400)
    header_block[0:5] = b"DAHUA"
    header_block[0x200 : 0x200 + 7] = b"DHFS4.1"
    chunks: list[bytes] = [bytes(header_block), b"CPPLUS LAB SPECIMEN\x00" + b"\x00" * 200]

    frame_number = 0
    index = 0
    for channel in (1, 1, 2, 1, 2):
        # I-frame then contiguous P-frames (single GOP per channel burst)
        chunks.append(_video_frame(DHAV_TYPE_I, channel, frame_number, index))
        frame_number += 1
        index += 1
        for _ in range(2):
            chunks.append(_video_frame(DHAV_TYPE_P, channel, frame_number, index))
            frame_number += 1
            index += 1
        chunks.append(b"\xff" * 64)

    chunks.append(b"\x00" * 8192)
    chunks.append(_video_frame(DHAV_TYPE_I, channel=1, frame_number=frame_number, index=index))
    frame_number += 1
    index += 1
    chunks.append(b"\x00" * 4096)

    for channel in (2, 2, 1):
        chunks.append(_video_frame(DHAV_TYPE_I, channel, frame_number, index))
        frame_number += 1
        index += 1
        chunks.append(b"\xee" * 32)

    return b"".join(chunks)


def write_lab_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_dahua_lab_specimen())
    return dest
