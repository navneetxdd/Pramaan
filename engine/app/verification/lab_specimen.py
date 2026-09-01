from __future__ import annotations

from pathlib import Path

from engine.app.parsers.schemas.dhav import (
    DhavHeaderStruct,
    seal_dhav_frame,
)
from engine.app.verification.media_fixture import NalPayloadSource

# Base Unix time for synthetic recorder clock in lab specimens.
_LAB_EPOCH_UNIX = 1_700_000_000
_nal_source = NalPayloadSource()


def _dhav_frame(payload_len: int, channel: int, *, recorder_unix: int) -> bytes:
    """Build a 4-check-valid DHAV frame (header + payload + checksum + footer)."""
    body_len = payload_len - 32 - 1 - 4
    if body_len < 8:
        raise ValueError("payload_len too small for specimen frame")
    payload = _nal_source.next_payload(body_len)
    if len(payload) > body_len:
        payload = payload[:body_len]
    header = DhavHeaderStruct.build(
        {
            "frame_len": payload_len,
            "reserved0": [0, 0, 0, 0],
            "channel": channel & 0x3F,
            "recorder_unix": recorder_unix,
            "header_pad": [0] * 15,
        }
    )
    return seal_dhav_frame(header, payload)


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
