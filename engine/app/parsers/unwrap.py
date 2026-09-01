from __future__ import annotations

import struct

from engine.app.parsers.schemas.dhav import DHAV_FOOTER, DHAV_HEADER, parse_dhav_frame_len, validate_dhav_frame

NAL_START_3 = b"\x00\x00\x01"
NAL_START_4 = b"\x00\x00\x00\x01"


def unwrap_to_h264(blob: bytes) -> bytes:
    if blob.startswith(DHAV_HEADER):
        return _unwrap_dhav_frames(blob)
    nal_idx = blob.find(NAL_START_4)
    if nal_idx < 0:
        nal_idx = blob.find(NAL_START_3)
    if nal_idx > 0:
        return blob[nal_idx:]
    return blob


def _unwrap_dhav_frames(data: bytes) -> bytes:
    out = bytearray()
    offset = 0
    while offset + 16 < len(data):
        if data[offset : offset + 4] != DHAV_HEADER:
            offset += 1
            continue
        parsed = validate_dhav_frame(data, offset)
        if not parsed or not parsed.checks["size_consistency"]:
            offset += 4
            continue
        frame_len = parsed.frame_len
        payload = data[offset + 32 : offset + frame_len - len(DHAV_FOOTER) - 1]
        if NAL_START_3 in payload or NAL_START_4 in payload:
            out.extend(payload)
        offset += frame_len
    return bytes(out) if out else data
