from __future__ import annotations

from pathlib import Path

from engine.app.parsers.schemas.hkvi import seal_hkvi_block
from engine.app.verification.media_fixture import NalPayloadSource

# Signatures from published Hikvision forensic literature (512/1024/2048 byte offsets).
HIKVISION_OEM_MARKERS = [
    b"HIKVISION@HANGZHOU\x00",
    b"HIKVISION-DVR\x00",
    b"HIKV\x00",
]

_nal_source = NalPayloadSource()


def _hkvi_payload(min_len: int) -> bytes:
    payload = _nal_source.next_payload(min_len)
    if len(payload) > min_len:
        return payload[:min_len]
    return payload + b"\x00" * (min_len - len(payload))


def build_hikvision_lab_specimen() -> bytes:
    """Synthetic Hikvision disk with OEM markers, HKVI blocks, and deleted slack."""
    chunks: list[bytes] = [
        b"\x00" * 512,
        HIKVISION_OEM_MARKERS[0] + b"\x00" * 480,
        b"\x00" * 512,
        b"HIKBTREE\x00" + b"\x00" * 504,
        b"WFS0.4\x00" + b"\x00" * 506,
    ]

    for channel in (1, 1, 2, 1):
        payload = _hkvi_payload(176)
        chunks.append(seal_hkvi_block(payload, channel=channel))
        chunks.append(b"\xff" * 48)

    chunks.append(b"\x00" * 16384)
    chunks.append(seal_hkvi_block(_hkvi_payload(192), channel=2))
    chunks.append(b"\x00" * 8192)

    for channel in (3, 3, 1):
        payload = _hkvi_payload(160)
        chunks.append(seal_hkvi_block(payload, channel=channel))
        chunks.append(b"\xee" * 32)

    return b"".join(chunks)


def write_hikvision_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_hikvision_lab_specimen())
    return dest
