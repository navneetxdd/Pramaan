from __future__ import annotations

from pathlib import Path

from engine.app.parsers.schemas.dhav import (
    DHAV_FOOTER,
    DhavHeaderStruct,
    compute_dhav_checksum,
)
from engine.app.parsers.unwrap import NAL_START_4

_H264_IDR_STUB = NAL_START_4 + bytes([0x65, 0x88, 0x84, 0x00, 0x10]) + (b"\x00" * 120)

# Base Unix time for synthetic recorder clock in lab specimens.
_LAB_EPOCH_UNIX = 1_700_000_000


def _dhav_frame(payload_len: int, channel: int, *, recorder_unix: int) -> bytes:
    """Build a 4-check-valid DHAV frame (header + payload + checksum + footer)."""
    body_len = payload_len - 32 - 1 - 4
    if body_len < len(_H264_IDR_STUB):
        raise ValueError("payload_len too small for specimen frame")
    payload = _H264_IDR_STUB + (b"\x00" * (body_len - len(_H264_IDR_STUB)))
    header = DhavHeaderStruct.build(
        {
            "frame_len": payload_len,
            "reserved0": [0, 0, 0, 0],
            "channel": channel & 0x3F,
            "recorder_unix": recorder_unix,
            "header_pad": [0] * 15,
        }
    )
    body = header + payload
    checksum = compute_dhav_checksum(body)
    return body + bytes([checksum]) + DHAV_FOOTER


def build_dahua_lab_specimen() -> bytes:
    """
    Synthetic bitstream with DHAV frames and OEM markers.
    Includes an orphaned frame after zero slack — recovered as unreferenced_carve, not deleted.
    """
    chunks: list[bytes] = [
        b"DHFS4.1\x00" + b"\x00" * 512,
        b"CPPLUS LAB SPECIMEN\x00" + b"\x00" * 240,
        b"Dahua Technology\x00" + b"\x00" * 128,
    ]

    frame_index = 0
    for channel in (1, 1, 2, 1, 2):
        chunks.append(_dhav_frame(512, channel, recorder_unix=_LAB_EPOCH_UNIX + frame_index * 60))
        frame_index += 1
        chunks.append(b"\xff" * 64)

    chunks.append(b"\x00" * 8192)
    chunks.append(_dhav_frame(384, channel=1, recorder_unix=_LAB_EPOCH_UNIX + frame_index * 60))
    frame_index += 1
    chunks.append(b"\x00" * 4096)

    for channel in (2, 2, 1):
        chunks.append(_dhav_frame(448, channel, recorder_unix=_LAB_EPOCH_UNIX + frame_index * 60))
        frame_index += 1
        chunks.append(b"\xee" * 32)

    return b"".join(chunks)


def write_lab_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_dahua_lab_specimen())
    return dest
