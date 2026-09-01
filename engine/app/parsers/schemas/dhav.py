from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone

DHAV_HEADER = b"DHAV"
DHAV_FOOTER = b"dhav"
DHAV_HEADER_SIZE = 24
DHAV_FOOTER_SIZE = 8  # magic(4) + seek_back u32

# Frame types (libavformat/dhav.c)
DHAV_TYPE_I = 0xFD
DHAV_TYPE_P = 0xFC
DHAV_TYPE_AUDIO = 0xF0
DHAV_TYPE_INFO = 0xF1

# Extension TLV consume sizes
_EXT_CONSUME: dict[int, int] = {
    0x80: 4,
    0x81: 4,
    0x82: 8,
    0x83: 4,
    0x84: 4,
    0x85: 4,
    0x88: 8,
    0x8B: 4,
    0x8C: 8,
    0x91: 8,
    0x92: 8,
    0x93: 8,
    0x94: 4,
    0x95: 8,
    0x96: 4,
    0x9A: 8,
    0x9B: 8,
    0xA0: 4,
    0xB2: 4,
    0xB3: 8,
    0xB4: 4,
}


@dataclass(frozen=True)
class DhavValidationResult:
    ok: bool
    frame_len: int
    frame_type: int
    channel: int
    frame_number: int
    recorder_unix: int | None
    timestamp_source: str
    checks: dict[str, bool]
    validation_level: str

    @property
    def confidence(self) -> float:
        passed = sum(1 for v in self.checks.values() if v)
        if passed >= 5:
            return 0.95
        if passed >= 3:
            return 0.72
        return 0.45

    @property
    def recorder_iso(self) -> str | None:
        if self.recorder_unix is None or self.recorder_unix <= 0:
            return None
        try:
            return datetime.fromtimestamp(int(self.recorder_unix), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None


def pack_dhav_date(dt: datetime) -> int:
    return (
        (dt.second & 0x3F)
        | ((dt.minute & 0x3F) << 6)
        | ((dt.hour & 0x1F) << 12)
        | ((dt.day & 0x1F) << 17)
        | ((dt.month & 0xF) << 22)
        | (((dt.year - 2000) & 0x3F) << 26)
    )


def unpack_dhav_date(date_val: int) -> datetime | None:
    year = ((date_val >> 26) & 0x3F) + 2000
    if year <= 2000:
        return None
    month = (date_val >> 22) & 0xF
    day = (date_val >> 17) & 0x1F
    hour = (date_val >> 12) & 0x1F
    minute = (date_val >> 6) & 0x3F
    second = date_val & 0x3F
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        return None


def dhav_datetime_to_unix(date_val: int, timestamp_ms: int) -> int | None:
    dt = unpack_dhav_date(date_val)
    if dt is None:
        return None
    return int(dt.timestamp()) + int(timestamp_ms) // 1000


def build_h264_ext_tlvs(width: int = 320, height: int = 240, fps: int = 6) -> bytes:
    """0x81 codec + 0x80 resolution TLVs."""
    return bytes([0x81, 0, 0x08, fps, 0x80, 0, width // 8, height // 8])


def _header_checksum(header_23: bytes) -> int:
    return sum(header_23[:23]) & 0xFF


def seal_dhav_video_frame(
    *,
    frame_type: int,
    channel: int,
    frame_number: int,
    when: datetime,
    payload: bytes,
    ext: bytes | None = None,
    subtype: int = 0,
    frame_subnumber: int = 0,
) -> bytes:
    if frame_type not in {DHAV_TYPE_I, DHAV_TYPE_P, DHAV_TYPE_AUDIO}:
        raise ValueError(f"unsupported video frame type {frame_type:#x}")
    ext = ext or b""
    date_val = pack_dhav_date(when)
    ts_ms = when.microsecond // 1000
    frame_len = DHAV_HEADER_SIZE + len(ext) + len(payload) + DHAV_FOOTER_SIZE
    header = bytearray(DHAV_HEADER_SIZE)
    header[0:4] = DHAV_HEADER
    header[4] = frame_type & 0xFF
    header[5] = subtype & 0xFF
    header[6] = channel & 0xFF
    header[7] = frame_subnumber & 0xFF
    struct.pack_into("<I", header, 8, frame_number & 0xFFFFFFFF)
    struct.pack_into("<I", header, 12, frame_len)
    struct.pack_into("<I", header, 16, date_val)
    struct.pack_into("<H", header, 20, ts_ms & 0xFFFF)
    header[22] = len(ext) & 0xFF
    header[23] = _header_checksum(bytes(header))
    seek_back = frame_len - 8
    footer = DHAV_FOOTER + struct.pack("<I", seek_back)
    return bytes(header) + ext + payload + footer


def validate_dhav_frame(data: bytes, offset: int = 0) -> DhavValidationResult | None:
    if offset + DHAV_HEADER_SIZE > len(data):
        return None
    if data[offset : offset + 4] != DHAV_HEADER:
        return None

    frame_type = data[offset + 4]
    channel = data[offset + 6]
    frame_number = struct.unpack_from("<I", data, offset + 8)[0]
    frame_len = struct.unpack_from("<I", data, offset + 12)[0]
    date_val = struct.unpack_from("<I", data, offset + 16)[0]
    timestamp_ms = struct.unpack_from("<H", data, offset + 20)[0]
    ext_length = data[offset + 22]
    header_checksum = data[offset + 23]

    checks = {
        "header_signature": True,
        "valid_frame_type": frame_type in {DHAV_TYPE_I, DHAV_TYPE_P, DHAV_TYPE_AUDIO, DHAV_TYPE_INFO},
        "size_consistency": False,
        "footer_signature": False,
        "seek_back": False,
        "checksum": _header_checksum(data[offset : offset + 23]) == header_checksum,
    }

    end = offset + frame_len
    if frame_len < DHAV_HEADER_SIZE + DHAV_FOOTER_SIZE or end > len(data):
        return DhavValidationResult(
            False,
            frame_len,
            frame_type,
            channel,
            frame_number,
            None,
            "unavailable",
            checks,
            "truncated",
        )

    checks["size_consistency"] = True
    footer_start = end - DHAV_FOOTER_SIZE
    checks["footer_signature"] = data[footer_start : footer_start + 4] == DHAV_FOOTER
    seek_back = struct.unpack_from("<I", data, footer_start + 4)[0]
    checks["seek_back"] = seek_back == frame_len - 8

    recorder_unix = dhav_datetime_to_unix(date_val, timestamp_ms)
    ts_source = "dhav_header_date" if recorder_unix else "unavailable"
    all_ok = all(checks.values())
    level = "dual_signature_4" if all_ok else "header_footer_only"
    return DhavValidationResult(
        all_ok,
        frame_len,
        frame_type,
        channel,
        frame_number,
        recorder_unix,
        ts_source,
        checks,
        level,
    )


def parse_dhav_frame_len(data: bytes, offset: int) -> int | None:
    result = validate_dhav_frame(data, offset)
    return result.frame_len if result and result.checks["size_consistency"] else None


# Backward-compatible aliases used by older call sites during migration
def seal_dhav_frame(header: bytes, payload: bytes) -> bytes:
    raise NotImplementedError("use seal_dhav_video_frame() with the FFmpeg DHAV layout")


def build_dhav_timestamp_tlv(unix: int) -> bytes:
    raise NotImplementedError("DHAV uses header date bitfield, not 0x72 TLV")


def parse_dhav_timestamp_tlv(payload: bytes) -> int | None:
    return None


def resolve_dhav_timestamp(header_unix: int | None, payload: bytes) -> tuple[int | None, str]:
    if header_unix and header_unix > 0:
        return header_unix, "recorder_header"
    return None, "unavailable"
