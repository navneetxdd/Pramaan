from __future__ import annotations

import struct
from pathlib import Path

from pramaan.recovery.base import RecoveredSegment

HKVI_MAGIC = b"HKVI"
MAX_BLOCK = 8 * 1024 * 1024


class HikvisionAdapter:
    name = "hikvision"
    vendor = "Hikvision"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        segments: list[RecoveredSegment] = []
        chunk_size = 8 * 1024 * 1024
        carry = b""
        offset_base = 0
        total_read = 0

        with image_path.open("rb") as handle:
            while True:
                if max_bytes is not None and total_read >= max_bytes:
                    break
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                total_read += len(chunk)
                window = carry + chunk
                idx = 0
                while True:
                    hit = window.find(HKVI_MAGIC, idx)
                    if hit < 0:
                        break
                    block_len = _infer_hik_block_len(window, hit)
                    if block_len:
                        abs_start = offset_base - len(carry) + hit
                        abs_end = abs_start + block_len
                        channel = _extract_channel(window, hit)
                        segments.append(
                            RecoveredSegment(
                                channel=channel,
                                vendor=self.vendor,
                                offset_start=abs_start,
                                offset_end=abs_end,
                                frame_count=1,
                                confidence=0.86,
                                validation="hkvi_block",
                                raw_bytes=window[hit : hit + block_len],
                            )
                        )
                        idx = hit + block_len
                    else:
                        idx = hit + 4
                carry = window[-128:]
                offset_base += len(chunk)

        return _merge(segments)


def _infer_hik_block_len(window: bytes, hit: int) -> int | None:
    if hit + 16 > len(window):
        return None
    # Common Hikvision index blocks encode payload length after magic.
    for offset in (8, 12, 16):
        if hit + offset + 4 > len(window):
            continue
        candidate = struct.unpack_from("<I", window, hit + offset)[0]
        if 256 <= candidate <= MAX_BLOCK and hit + candidate <= len(window):
            return candidate
    # Fallback fixed probe window for partial blocks at chunk edges
    fallback = min(256 * 1024, len(window) - hit)
    return fallback if fallback >= 256 else None


def _extract_channel(window: bytes, hit: int) -> int | None:
    if hit + 20 > len(window):
        return None
    value = window[hit + 16]
    return int(value) if value < 64 else None


def _merge(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    segments.sort(key=lambda s: s.offset_start)
    out = [segments[0]]
    for seg in segments[1:]:
        prev = out[-1]
        if seg.offset_start <= prev.offset_end + 8192 and seg.channel == prev.channel:
            out[-1] = RecoveredSegment(
                channel=prev.channel,
                vendor=prev.vendor,
                offset_start=prev.offset_start,
                offset_end=max(prev.offset_end, seg.offset_end),
                frame_count=prev.frame_count + seg.frame_count,
                confidence=min(prev.confidence, seg.confidence),
                validation=prev.validation,
                raw_bytes=b"",
            )
        else:
            out.append(seg)
    return out
