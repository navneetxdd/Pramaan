from __future__ import annotations

from dataclasses import dataclass

from construct import Const, Int32ul, Int8ul, Struct

HKVI_MAGIC = b"HKVI"
HKVI_HEADER_SIZE = 32
HKVI_TRAILER = b"IVKH"

HkviHeaderStruct = Struct(
    "magic" / Const(HKVI_MAGIC),
    "version" / Int8ul[4],
    "payload_len" / Int32ul,
    "channel" / Int8ul,
    "header_pad" / Int8ul[18],
    "checksum" / Int8ul,
)


@dataclass(frozen=True)
class HkviValidationResult:
    ok: bool
    block_len: int
    channel: int
    checks: dict[str, bool]
    validation_level: str

    @property
    def confidence(self) -> float:
        passed = sum(1 for v in self.checks.values() if v)
        if passed == 4:
            return 0.9
        if passed >= 2:
            return 0.68
        return 0.42


def compute_hkvi_checksum(header_without_checksum: bytes) -> int:
    return sum(header_without_checksum[: HKVI_HEADER_SIZE - 1]) & 0xFF


def seal_hkvi_block(payload: bytes, *, channel: int = 0, version: bytes = b"\x01\x00\x00\x00") -> bytes:
    block_len = HKVI_HEADER_SIZE + len(payload) + 4
    header_body = HkviHeaderStruct.build(
        {
            "version": list(version[:4].ljust(4, b"\x00")),
            "payload_len": block_len,
            "channel": channel & 0x3F,
            "header_pad": [0] * 18,
            "checksum": 0,
        }
    )
    checksum = compute_hkvi_checksum(header_body)
    header = header_body[:-1] + bytes([checksum])
    return header + payload + HKVI_TRAILER


def validate_hkvi_block(data: bytes, offset: int = 0) -> HkviValidationResult | None:
    if offset + HKVI_HEADER_SIZE + 4 > len(data):
        return None
    if data[offset : offset + 4] != HKVI_MAGIC:
        return None

    try:
        parsed = HkviHeaderStruct.parse(data[offset : offset + HKVI_HEADER_SIZE])
    except Exception:
        return None

    block_len = int(parsed.payload_len)
    checks = {
        "header_signature": data[offset : offset + 4] == HKVI_MAGIC,
        "trailer_signature": False,
        "size_consistency": False,
        "checksum": False,
    }

    end = offset + block_len
    if block_len < HKVI_HEADER_SIZE + 4:
        return HkviValidationResult(False, block_len, int(parsed.channel), checks, "invalid_length")

    if end > len(data):
        return HkviValidationResult(False, block_len, int(parsed.channel), checks, "truncated")

    checks["size_consistency"] = True
    checks["trailer_signature"] = data[end - 4 : end] == HKVI_TRAILER

    header_bytes = data[offset : offset + HKVI_HEADER_SIZE]
    expected = compute_hkvi_checksum(header_bytes)
    actual = int(parsed.checksum)
    checks["checksum"] = expected == actual

    all_ok = all(checks.values())
    level = "hkvi_block_4" if all_ok else "hkvi_header_only"
    return HkviValidationResult(all_ok, block_len, int(parsed.channel), checks, level)
