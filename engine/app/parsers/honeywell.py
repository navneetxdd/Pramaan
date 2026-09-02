from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from typing import BinaryIO
from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.generic_fallback import H264CarveAdapter
from engine.app.parsers.schemas.honeywell import (
    NAL_START_4,
    VIDEO_CHANNEL_LIST_OFFSET,
    detect_honeywell_layout,
    frame_length_bytes,
    parse_channel_entry,
)

logger = logging.getLogger("forensic.engine")


class HoneywellAdapter:
    name = "honeywell"
    vendor = "Honeywell"
    version = "2"
    _LAYOUT_WINDOW = 5 * 1024 * 1024
    _SCAN_CHUNK = 4 * 1024 * 1024
    _MAX_FRAME_BYTES = 64 * 1024 * 1024

    def __init__(self) -> None:
        self._carve_fallback = H264CarveAdapter()

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        file_size = image_path.stat().st_size
        scan_end = min(file_size, max_bytes) if max_bytes is not None else file_size
        with image_path.open("rb") as handle:
            layout_bytes = handle.read(min(self._LAYOUT_WINDOW, scan_end))
            layout = detect_honeywell_layout(layout_bytes)
            if layout is None:
                logger.info("Honeywell GPT layout not detected — falling back to H.264 carve")
                return self._carve_with_vendor(self._carve_fallback.scan(image_path, max_bytes=max_bytes))
            segments: list[RecoveredSegment] = []
            segments.extend(self._recover_expiration_deletion(handle, layout, scan_end))
            segments.extend(self._recover_format_deletion(handle, layout, scan_end))
        if not segments:
            segments = self._carve_with_vendor(self._carve_fallback.scan(image_path, max_bytes=max_bytes))
        return _merge_segments(segments)

    def _recover_expiration_deletion(self, handle: BinaryIO, layout, scan_end: int) -> list[RecoveredSegment]:
        """Recover indexed frames with timestamps older than the header start-time."""
        segments: list[RecoveredSegment] = []
        list_base = layout.partition_base + VIDEO_CHANNEL_LIST_OFFSET
        offset = list_base
        while offset + 16 <= scan_end:
            handle.seek(offset)
            entry, ok = parse_channel_entry(handle.read(16), 0)
            if not ok:
                break
            ts = int(entry["frame_start_time"])
            channel = int(entry["channel_id"])
            frame_off = int(entry["frame_start_offset"])
            length = frame_length_bytes(int(entry["frame_length_rounded"]))
            is_deleted = ts < layout.header_start_time
            if frame_off + 32 <= scan_end:
                parsed = self._read_nal_header(handle, frame_off, scan_end)
                if parsed:
                    total, meta = parsed
                    validation = "honeywell_expired_index" if is_deleted else "honeywell_index_4"
                    confidence = 0.88 if is_deleted else 0.91
                    segments.append(
                        RecoveredSegment(
                            channel=channel,
                            vendor=self.vendor,
                            offset_start=frame_off,
                            offset_end=frame_off + total,
                            frame_count=1,
                            confidence=confidence,
                            validation=validation,
                            raw_bytes=b"",
                            codec="h264",
                            recorder_start_ts=_epoch_seconds(ts),
                            recorder_end_ts=_epoch_seconds(ts),
                            timestamp_source="honeywell_channel_index",
                            timestamp_confidence=0.82,
                            parser_name=self.name,
                            parser_version=self.version,
                            signature_evidence={"nal_marker": "800100", "index_entry": True},
                            validation_evidence={
                                "indexed_length": length,
                                "validated_length": total,
                                "expired_index_entry": is_deleted,
                            },
                        )
                    )
                elif frame_off + length <= scan_end:
                    validation = "honeywell_expired_index" if is_deleted else "honeywell_index"
                    segments.append(
                        RecoveredSegment(
                            channel=channel,
                            vendor=self.vendor,
                            offset_start=frame_off,
                            offset_end=frame_off + length,
                            frame_count=1,
                            confidence=0.78 if is_deleted else 0.82,
                            validation=validation,
                            raw_bytes=b"",
                            recorder_start_ts=_epoch_seconds(ts),
                            recorder_end_ts=_epoch_seconds(ts),
                            timestamp_source="honeywell_channel_index",
                            timestamp_confidence=0.7,
                            parser_name=self.name,
                            parser_version=self.version,
                            signature_evidence={"index_entry": True},
                            validation_evidence={"indexed_length": length, "expired_index_entry": is_deleted},
                        )
                    )
            offset += 16
        return segments

    def _recover_format_deletion(self, handle: BinaryIO, layout, scan_end: int) -> list[RecoveredSegment]:
        """Scan raw video region for custom NAL headers (post-format metadata wipe)."""
        segments: list[RecoveredSegment] = []
        start = layout.video_data_start
        end = scan_end
        offset = start
        while offset + 40 < end:
            handle.seek(offset)
            chunk = handle.read(min(self._SCAN_CHUNK, end - offset))
            if not chunk:
                break
            local = 0
            while local + 20 <= len(chunk):
                hit = chunk.find(b"\x80\x01\x00", local + 1)
                if hit < 1:
                    break
                absolute = offset + hit - 1
                parsed = self._read_nal_header(handle, absolute, end)
                if parsed:
                    total, meta = parsed
                    timestamp_us = int(meta["timestamp_us"])
                    recorder_ts = _epoch_microseconds(timestamp_us)
                    segments.append(
                        RecoveredSegment(
                            channel=int(meta["frame_type"]) & 0x0F or 1,
                            vendor=self.vendor,
                            offset_start=absolute,
                            offset_end=absolute + total,
                            frame_count=1,
                            confidence=0.9,
                            validation="honeywell_format_carve_4",
                            raw_bytes=b"",
                            codec="h264",
                            recorder_start_ts=recorder_ts,
                            recorder_end_ts=recorder_ts,
                            timestamp_source="honeywell_nal_timestamp_us",
                            timestamp_confidence=0.88,
                            parser_name=self.name,
                            parser_version=self.version,
                            signature_evidence={"nal_marker": "800100", "annex_b_start_code": True},
                            validation_evidence={"bounded_frame_length": total},
                        )
                    )
                    local = hit + total
                else:
                    local = hit + 1
            offset += max(len(chunk) - 19, 1)
        return segments

    def _read_nal_header(self, handle: BinaryIO, offset: int, scan_end: int) -> tuple[int, dict] | None:
        handle.seek(offset)
        header = handle.read(20)
        if len(header) < 20 or header[0] not in {0x82, 0x02} or header[1:4] != b"\x80\x01\x00":
            return None
        nal_length = struct.unpack_from("<I", header, 8)[0]
        payload_prefix = handle.read(6)
        if len(payload_prefix) < 4:
            return None
        if not (payload_prefix.startswith(NAL_START_4) or payload_prefix.startswith(b"\x00\x00\x01")):
            return None
        total = 20 + nal_length
        if total > self._MAX_FRAME_BYTES or offset + total > scan_end:
            return None
        return total, {
            "frame_type": header[0],
            "timestamp_us": struct.unpack_from("<Q", header, 12)[0],
        }

    def _carve_with_vendor(self, segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
        return [
            RecoveredSegment(
                channel=seg.channel,
                vendor=self.vendor,
                offset_start=seg.offset_start,
                offset_end=seg.offset_end,
                frame_count=seg.frame_count,
                confidence=min(seg.confidence, 0.65),
                validation="honeywell_gpt_carve",
                raw_bytes=seg.raw_bytes,
                codec=seg.codec or "h264",
                parser_name=self.name,
                parser_version=self.version,
                signature_evidence={"honeywell_layout": False, **seg.signature_evidence},
                validation_evidence=seg.validation_evidence,
            )
            for seg in segments
        ]


def _merge_segments(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    seen: set[tuple[int, int]] = set()
    out: list[RecoveredSegment] = []
    for seg in sorted(segments, key=lambda s: s.offset_start):
        key = (seg.offset_start, seg.offset_end)
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def _epoch_seconds(value: int) -> str | None:
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _epoch_microseconds(value: int) -> str | None:
    return _epoch_seconds(value // 1_000_000) if value > 0 else None
