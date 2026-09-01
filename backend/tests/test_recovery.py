import struct
import tempfile
from pathlib import Path

import pytest

from pramaan.recovery.adapters.dahua_dhav import DHAV_FOOTER, DHAV_HEADER, DahuaDhavAdapter, detect_vendors


def _build_dhav_frame(payload_len: int = 256, channel: int = 3) -> bytes:
    header = DHAV_HEADER + struct.pack("<I", payload_len) + bytes([0, 0, channel, 0])
    body_len = payload_len - len(header) - len(DHAV_FOOTER)
    if body_len < 0:
        raise ValueError("payload_len too small")
    return header + (b"\x00" * body_len) + DHAV_FOOTER


def test_dhav_dual_signature_carve():
    frame = _build_dhav_frame(256)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"\xff" * 1024)
        tmp.write(frame)
        tmp.write(b"\xff" * 1024)
        path = Path(tmp.name)

    adapter = DahuaDhavAdapter()
    segments = adapter.scan(path)
    assert len(segments) >= 1
    assert segments[0].validation == "dual_signature"
    path.unlink(missing_ok=True)


def test_vendor_detection_dahua():
    frame = _build_dhav_frame(512)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(frame * 4)
        path = Path(tmp.name)
    hits = detect_vendors(path)
    assert hits
    assert hits[0].vendor == "Dahua"
    path.unlink(missing_ok=True)
