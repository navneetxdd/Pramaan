from __future__ import annotations

import struct

NAL_START_3 = b"\x00\x00\x01"
NAL_START_4 = b"\x00\x00\x00\x01"
DHAV_HEADER = b"DHAV"
DHAV_FOOTER = b"dhav"


def unwrap_to_h264(blob: bytes) -> bytes:
    """Extract H.264 payload from DHAV container bytes or return raw NAL stream."""
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
        frame_len = struct.unpack_from("<I", data, offset + 4)[0]
        if frame_len < 32 or offset + frame_len > len(data):
            offset += 4
            continue
        if data[offset + frame_len - 4 : offset + frame_len] != DHAV_FOOTER:
            offset += 4
            continue
        payload = data[offset + 32 : offset + frame_len - 4]
        if NAL_START_3 in payload or NAL_START_4 in payload:
            out.extend(payload)
        offset += frame_len
    return bytes(out) if out else data
