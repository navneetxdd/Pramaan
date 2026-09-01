from __future__ import annotations

from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.schemas.hkvi import HKVI_MAGIC, validate_hkvi_block


class HikvisionAdapter:
    name = "hikvision"
    vendor = "Hikvision"
    version = "2"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        segments: list[RecoveredSegment] = []
        chunk_size = 8 * 1024 * 1024
        carry = b""
        offset_base = 0
        total_read = 0
        hikbtree_seen = False

        with image_path.open("rb") as handle:
            while True:
                if max_bytes is not None and total_read >= max_bytes:
                    break
                read_size = chunk_size if max_bytes is None else min(chunk_size, max_bytes - total_read)
                chunk = handle.read(read_size)
                if not chunk:
                    break
                total_read += len(chunk)
                window = carry + chunk
                hikbtree_seen = hikbtree_seen or b"HIKBTREE" in window
                idx = 0
                while True:
                    hit = window.find(HKVI_MAGIC, idx)
                    if hit < 0:
                        break
                    parsed = validate_hkvi_block(window, hit)
                    if parsed and parsed.checks["size_consistency"]:
                        abs_start = offset_base - len(carry) + hit
                        abs_end = abs_start + parsed.block_len
                        segments.append(
                            RecoveredSegment(
                                channel=parsed.channel,
                                vendor=self.vendor,
                                offset_start=abs_start,
                                offset_end=abs_end,
                                frame_count=1,
                                confidence=parsed.confidence,
                                validation=parsed.validation_level,
                                raw_bytes=window[hit : hit + parsed.block_len],
                                codec="h264",
                                parser_name=self.name,
                                parser_version=self.version,
                                signature_evidence={
                                    "block_header": "HKVI",
                                    "block_trailer": "IVKH" if parsed.checks["trailer_signature"] else None,
                                    "hikbtree_index_seen": hikbtree_seen,
                                },
                                validation_evidence=parsed.checks,
                            )
                        )
                        idx = hit + parsed.block_len
                    else:
                        idx = hit + 4
                carry = window[-128:]
                offset_base += len(chunk)

        return _merge(segments)


def _merge(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    segments.sort(key=lambda s: s.offset_start)
    out = [segments[0]]
    for seg in segments[1:]:
        prev = out[-1]
        if seg.offset_start <= prev.offset_end and seg.channel == prev.channel:
            out[-1] = RecoveredSegment(
                channel=prev.channel,
                vendor=prev.vendor,
                offset_start=prev.offset_start,
                offset_end=max(prev.offset_end, seg.offset_end),
                frame_count=prev.frame_count + seg.frame_count,
                confidence=min(prev.confidence, seg.confidence),
                validation=prev.validation if prev.validation == seg.validation else "mixed",
                raw_bytes=b"",
                codec=prev.codec,
                parser_name=prev.parser_name,
                parser_version=prev.parser_version,
                signature_evidence={
                    "block_signatures": prev.frame_count + seg.frame_count,
                    "block_header": "HKVI",
                    "block_trailer": "IVKH",
                    "hikbtree_index_seen": bool(
                        prev.signature_evidence.get("hikbtree_index_seen")
                        or seg.signature_evidence.get("hikbtree_index_seen")
                    ),
                },
                validation_evidence={
                    "bounded_blocks": prev.frame_count + seg.frame_count,
                    "all_blocks_validated": all(
                        item.validation == "hkvi_block_4" for item in (prev, seg)
                    ),
                },
            )
        else:
            out.append(seg)
    return out
