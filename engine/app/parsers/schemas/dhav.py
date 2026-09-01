from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from construct import Const, Int32ul, Int8ul, Struct

DHAV_HEADER = b"DHAV"
DHAV_FOOTER = b"dhav"
DHAV_HEADER_SIZE = 32
DHAV_FOOTER_SIZE = 4
DHAV_CHECKSUM_SIZE = 1

# Lab/simplified extension: bytes 13–16 store a Unix timestamp (real Dahua uses TLV 0x70).
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
        if self.recorder_unix is None or self.recorder_unix <= 0:
            return None
        try:
            return datetime.fromtimestamp(int(self.recorder_unix), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None


def compute_dhav_checksum(frame: bytes) -> int:
    """Checksum covers header + payload (all bytes before checksum + footer)."""
    if len(frame) < DHAV_HEADER_SIZE + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE:
        return 0
    return sum(frame[:- (DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE)]) & 0xFF


def seal_dhav_frame(header: bytes, payload: bytes) -> bytes:
    """Build a spec-valid DHAV frame with checksum + footer."""
    if len(header) != DHAV_HEADER_SIZE:
        raise ValueError("DHAV header must be 32 bytes")
    parsed = DhavHeaderStruct.parse(header)
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
    recorder_unix = int(parsed.recorder_unix) if int(parsed.recorder_unix) > 0 else None
    checks = {
        "header_signature": data[offset : offset + 4] == DHAV_HEADER,
        "footer_signature": False,
        "size_consistency": False,
        "checksum": False,
    }

    end = offset + frame_len
    if frame_len < DHAV_HEADER_SIZE + DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE:
        return DhavValidationResult(
            False, frame_len, int(parsed.channel), recorder_unix, checks, "invalid_length"
        )

    if end > len(data):
        return DhavValidationResult(False, frame_len, int(parsed.channel), recorder_unix, checks, "truncated")

    checks["size_consistency"] = True
    checks["footer_signature"] = data[end - DHAV_FOOTER_SIZE : end] == DHAV_FOOTER

    frame_slice = data[offset:end]
    expected_checksum = compute_dhav_checksum(frame_slice)
    actual_checksum = frame_slice[- (DHAV_CHECKSUM_SIZE + DHAV_FOOTER_SIZE)]
    checks["checksum"] = expected_checksum == actual_checksum

    all_ok = all(checks.values())
    level = "dual_signature_4" if all_ok else "header_footer_only"
    return DhavValidationResult(all_ok, frame_len, int(parsed.channel), recorder_unix, checks, level)


def parse_dhav_frame_len(data: bytes, offset: int) -> int | None:
    result = validate_dhav_frame(data, offset)
    return result.frame_len if result and result.checks["size_consistency"] else None
