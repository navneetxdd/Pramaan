from __future__ import annotations

from pathlib import Path

from engine.app.parsers.schemas.hkvi import seal_hkvi_block

# Signatures from published Hikvision forensic literature (512/1024/2048 byte offsets).
HIKVISION_OEM_MARKERS = [
    b"HIKVISION@HANGZHOU\x00",
    b"HIKVISION-DVR\x00",
    b"HIKV\x00",
]


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
        payload = b"\x00" * 96 + b"\x00\x00\x00\x01\x65" + (b"\xab" * 80)
        chunks.append(seal_hkvi_block(payload, channel=channel))
        chunks.append(b"\xff" * 48)

    chunks.append(b"\x00" * 16384)
    orphan_payload = b"\x00" * 128 + b"\x00\x00\x00\x01\x65" + (b"\xcd" * 64)
    chunks.append(seal_hkvi_block(orphan_payload, channel=2))
    chunks.append(b"\x00" * 8192)

    for channel in (3, 3, 1):
        payload = b"\x00" * 64 + b"\x00\x00\x00\x01\x41" + (b"\xee" * 96)
        chunks.append(seal_hkvi_block(payload, channel=channel))
        chunks.append(b"\xee" * 32)

    return b"".join(chunks)


def write_hikvision_specimen(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(build_hikvision_lab_specimen())
    return dest
