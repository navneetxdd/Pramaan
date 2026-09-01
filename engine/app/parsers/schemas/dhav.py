from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from construct import Const, Int32ul, Int8ul, Struct

DHAV_HEADER = b"DHAV"
DHAV_FOOTER = b"dhav"
DHAV_HEADER_SIZE = 32
DHAV_FOOTER_SIZE = 4
DHAV_CHECKSUM_SIZE = 1
DHAV_EXT_TIMESTAMP = 0x72

# Lab/simplified extension: bytes 13–16 store a legacy Unix timestamp; real Dahua also uses TLV 0x72 in payload.
DhavHeaderStruct = Struct(
    "magic" / Const(DHAV_HEADER),
    "frame_len" / Int32ul,
    "reserved0" / Int8ul[4],
    "channel" / Int8ul,
    "recorder_unix" / Int32ul,
    "header_pad" / Int8ul[15],
)


@dataclass(frozen=True)
class DhavValidationResult:
    ok: bool
    frame_len: int
    channel: int
    recorder_unix: int | None
    timestamp_unix: int | None
    timestamp_source: str
    checks: dict[str, bool]
    validation_level: str

    @property
    def confidence(self) -> float:
        passed = sum(1 for v in self.checks.values() if v)
        if passed == 4:
            return 0.95
        if passed >= 2:
            return 0.72
        return 0.45

    @property
    def recorder_iso(self) -> str | None:
        ts = self.timestamp_unix if self.timestamp_unix and self.timestamp_unix > 0 else self.recorder_unix
        if ts is None or ts <= 0:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None


def parse_dhav_timestamp_tlv(payload: bytes) -> int | None:
    """Parse Dahua extension TLV type 0x72 (4-byte little-endian Unix epoch) from payload prefix."""
    if len(payload) < 6:
        return None
    if payload[0] != DHAV_EXT_TIMESTAMP or payload[1] != 4:
        return None
    value = int.from_bytes(payload[2:6], "little")
    return value if value > 0 else None


def build_dhav_timestamp_tlv(unix: int) -> bytes:
    return bytes([DHAV_EXT_TIMESTAMP, 4]) + int(unix).to_bytes(4, "little")


def resolve_dhav_timestamp(header_unix: int | None, payload: bytes) -> tuple[int | None, str]:
    tlv_unix = parse_dhav_timestamp_tlv(payload)
    if tlv_unix:
        return tlv_unix, "dhav_ext_0x72"
    if header_unix and header_unix > 0:
        return header_unix, "recorder_header"
    return None, "unavailable"


def compute_dhav_checksum(frame: bytes) -> int:
    """Checksum covers header + payload (all bytes before checksum + footer)."""
    if len(frame) < DHAV_HEADER_SIZE:
        return 0
    if (
        len(frame) >= DHAV_HEADER_SIZE + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE
        and frame[-DHAV_FOOTER_SIZE:] == DHAV_FOOTER
    ):
        payload = frame[: -(DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE)]
    else:
        payload = frame
    return sum(payload) & 0xFF


def seal_dhav_frame(header: bytes, payload: bytes) -> bytes:
    """Build a spec-valid DHAV frame with optional 0x72 timestamp TLV + checksum + footer."""
    if len(header) != DHAV_HEADER_SIZE:
        raise ValueError("DHAV header must be 32 bytes")
    parsed = DhavHeaderStruct.parse(header)
    header_unix = int(parsed.recorder_unix) if int(parsed.recorder_unix) > 0 else None
    if header_unix and not parse_dhav_timestamp_tlv(payload):
        payload = build_dhav_timestamp_tlv(header_unix) + payload
    frame_len = DHAV_HEADER_SIZE + len(payload) + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE
    header = DhavHeaderStruct.build(
        {
            "frame_len": frame_len,
            "reserved0": list(parsed.reserved0),
            "channel": parsed.channel,
            "recorder_unix": parsed.recorder_unix,
            "header_pad": list(parsed.header_pad),
        }
    )
    body = header + payload
    checksum = compute_dhav_checksum(body)
    return body + bytes([checksum]) + DHAV_FOOTER


def validate_dhav_frame(data: bytes, offset: int = 0) -> DhavValidationResult | None:
    if offset + DHAV_HEADER_SIZE + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE > len(data):
        return None
    if data[offset : offset + 4] != DHAV_HEADER:
        return None

    try:
        parsed = DhavHeaderStruct.parse(data[offset : offset + DHAV_HEADER_SIZE])
    except Exception:
        return None

    frame_len = int(parsed.frame_len)
    header_unix = int(parsed.recorder_unix) if int(parsed.recorder_unix) > 0 else None
    checks = {
        "header_signature": data[offset : offset + 4] == DHAV_HEADER,
        "footer_signature": False,
        "size_consistency": False,
        "checksum": False,
    }

    end = offset + frame_len
    if frame_len < DHAV_HEADER_SIZE + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE:
        return DhavValidationResult(
            False,
            frame_len,
            int(parsed.channel),
            header_unix,
            None,
            "unavailable",
            checks,
            "invalid_length",
        )

    if end > len(data):
        return DhavValidationResult(
            False,
            frame_len,
            int(parsed.channel),
            header_unix,
            None,
            "unavailable",
            checks,
            "truncated",
        )

    checks["size_consistency"] = True
    checks["footer_signature"] = data[end - DHAV_FOOTER_SIZE : end] == DHAV_FOOTER

    frame_slice = data[offset:end]
    expected_checksum = compute_dhav_checksum(frame_slice)
    actual_checksum = frame_slice[-(DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE)]
    checks["checksum"] = expected_checksum == actual_checksum

    payload_start = offset + DHAV_HEADER_SIZE
    payload_end = end - DHAV_CHECKSUM_SIZE - DHAV_FOOTER_SIZE
    payload = data[payload_start:payload_end]
    timestamp_unix, timestamp_source = resolve_dhav_timestamp(header_unix, payload)

    all_ok = all(checks.values())
    level = "dual_signature_4" if all_ok else "header_footer_only"
    return DhavValidationResult(
        all_ok,
        frame_len,
        int(parsed.channel),
        header_unix,
        timestamp_unix,
        timestamp_source,
        checks,
        level,
    )


def parse_dhav_frame_len(data: bytes, offset: int) -> int | None:
    result = validate_dhav_frame(data, offset)
    return result.frame_len if result and result.checks["size_consistency"] else None
