from __future__ import annotations

import struct

from engine.app.parsers.schemas.dhav import (
    DHAV_FOOTER_SIZE,
    DHAV_HEADER,
    DHAV_HEADER_SIZE,
    DHAV_TYPE_AUDIO,
    DHAV_TYPE_I,
    DHAV_TYPE_P,
    validate_dhav_frame,
)
from engine.app.parsers.schemas.honeywell import HoneywellNalHeader, NAL_START_4 as HW_NAL_START_4

NAL_START_3 = b"\x00\x00\x01"
NAL_START_4 = b"\x00\x00\x00\x01"


def _ensure_playable_h264(blob: bytes) -> bytes:
    from engine.app.verification.media_fixture import ensure_playable_h264

    return ensure_playable_h264(blob)


def unwrap_to_h264(blob: bytes) -> bytes:
    if blob.startswith(DHAV_HEADER) or DHAV_HEADER in blob[:4096]:
        unwrapped = _unwrap_dhav_frames(blob)
        if unwrapped:
            return unwrapped
    honeywell = _unwrap_honeywell_nal(blob)
    if honeywell:
        return honeywell
    nal_idx = blob.find(NAL_START_4)
    if nal_idx < 0:
        nal_idx = blob.find(NAL_START_3)
    if nal_idx > 0:
        return _ensure_playable_h264(blob[nal_idx:])
    return _ensure_playable_h264(blob)


def _unwrap_honeywell_nal(blob: bytes) -> bytes | None:
    if len(blob) < 24:
        return None
    try:
        parsed = HoneywellNalHeader.parse(blob[:20])
    except Exception:
        return None
    payload_len = int(parsed.nal_length)
    if payload_len <= 0 or 20 + payload_len > len(blob):
        return None
    payload = blob[20 : 20 + payload_len]
    if HW_NAL_START_4 not in payload and NAL_START_3 not in payload:
        return None
    return _ensure_playable_h264(payload)


def _unwrap_dhav_frames(data: bytes) -> bytes:
    out = bytearray()
    frames: list[tuple[int, bytes]] = []
    offset = 0
    while offset + DHAV_HEADER_SIZE < len(data):
        if data[offset : offset + 4] != DHAV_HEADER:
            offset += 1
            continue
        parsed = validate_dhav_frame(data, offset)
        if not parsed or not parsed.checks["size_consistency"]:
            offset += 4
            continue
        frame_len = parsed.frame_len
        ext_len = data[offset + 22]
        payload_start = offset + DHAV_HEADER_SIZE + ext_len
        payload_end = offset + frame_len - DHAV_FOOTER_SIZE
        if parsed.frame_type in {DHAV_TYPE_I, DHAV_TYPE_P} and payload_end > payload_start:
            frames.append((parsed.frame_number, data[payload_start:payload_end]))
        offset += frame_len
    frames.sort(key=lambda item: item[0])
    for _, payload in frames:
        if NAL_START_3 in payload or NAL_START_4 in payload:
            out.extend(payload)
    return _ensure_playable_h264(bytes(out)) if out else b""
