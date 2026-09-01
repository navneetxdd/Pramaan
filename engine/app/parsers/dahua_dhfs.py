from __future__ import annotations

from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.schemas.dhav import DHAV_HEADER, validate_dhav_frame

UNREFERENCED_GAP_BYTES = 4096


class DahuaDhavAdapter:
    name = "dahua_dhav"
    vendor = "Dahua"
    version = "3"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        segments: list[RecoveredSegment] = []
        chunk_size = 8 * 1024 * 1024
        overlap = 128
        offset_base = 0
        total_read = 0
        carry = b""
        prev_frame_end = 0

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
                local_offset = 0
                while True:
                    hit = window.find(DHAV_HEADER, local_offset)
                    if hit < 0:
                        break
                    parsed = validate_dhav_frame(window, hit)
                    if parsed and parsed.checks["size_consistency"]:
                        abs_start = offset_base - len(carry) + hit
                        abs_end = abs_start + parsed.frame_len
                        gap = max(0, abs_start - prev_frame_end)
                        validation = parsed.validation_level
                        if gap >= UNREFERENCED_GAP_BYTES:
                            validation = "unreferenced_carve"
                        recorder_ts = parsed.recorder_iso
                        segments.append(
                            RecoveredSegment(
                                channel=parsed.channel,
                                vendor=self.vendor,
                                offset_start=abs_start,
                                offset_end=abs_end,
                                frame_count=1,
                                confidence=parsed.confidence if validation != "unreferenced_carve" else 0.62,
                                validation=validation,
                                raw_bytes=window[hit : hit + parsed.frame_len],
                                codec="h264",
                                recorder_start_ts=recorder_ts,
                                recorder_end_ts=recorder_ts,
                                timestamp_source="recorder_header" if recorder_ts else "unavailable",
                                timestamp_confidence=0.85 if recorder_ts else None,
                                parser_name=self.name,
                                parser_version=self.version,
                                signature_evidence={
                                    "header": "DHAV",
                                    "footer": "dhav" if parsed.checks["footer_signature"] else None,
                                    "gap_bytes": gap if gap >= UNREFERENCED_GAP_BYTES else 0,
                                },
                                validation_evidence={
                                    **parsed.checks,
                                    "recovery_context": validation,
                                },
                            )
                        )
                        prev_frame_end = abs_end
                        local_offset = hit + parsed.frame_len
                    else:
                        local_offset = hit + 4

                carry = window[-overlap:] if len(window) > overlap else window
                offset_base += len(chunk)

        return _merge_adjacent(segments)


def _merge_adjacent(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    segments.sort(key=lambda s: s.offset_start)
    merged: list[RecoveredSegment] = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if (
            seg.channel == last.channel
            and seg.vendor == last.vendor
            and seg.validation == last.validation
            and seg.offset_start <= last.offset_end
        ):
            merged[-1] = RecoveredSegment(
                channel=last.channel,
                vendor=last.vendor,
                offset_start=last.offset_start,
                offset_end=max(last.offset_end, seg.offset_end),
                frame_count=last.frame_count + seg.frame_count,
                confidence=min(last.confidence, seg.confidence),
                validation=last.validation,
                raw_bytes=b"",
                codec=last.codec,
                recorder_start_ts=last.recorder_start_ts,
                recorder_end_ts=seg.recorder_end_ts or last.recorder_end_ts,
                timestamp_source=last.timestamp_source,
                timestamp_confidence=last.timestamp_confidence,
                parser_name=last.parser_name,
                parser_version=last.parser_version,
                signature_evidence={
                    "frame_signatures": last.frame_count + seg.frame_count,
                    "header": "DHAV",
                    "footer": "dhav",
                },
                validation_evidence={
                    "bounded_frames": last.frame_count + seg.frame_count,
                    "recovery_context": last.validation,
                },
            )
        else:
            merged.append(seg)
    return merged
