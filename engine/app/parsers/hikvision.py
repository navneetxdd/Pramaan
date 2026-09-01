from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.schemas.hikvision_fs import (
    MASTER_BLOCK_OFFSET,
    carve_mpegps_block,
    parse_hikbtree_entries,
    parse_master_block,
)


class HikvisionAdapter:
    name = "hikvision"
    vendor = "Hikvision"
    version = "3"

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        data = image_path.read_bytes() if max_bytes is None else image_path.read_bytes()[:max_bytes]
        master = parse_master_block(data, MASTER_BLOCK_OFFSET)
        if not master:
            return _scan_legacy_hikvi(image_path, max_bytes=max_bytes)

        tree_offset = int(master["hikbtree_offset"])
        entries = parse_hikbtree_entries(data, tree_offset)
        segments: list[RecoveredSegment] = []
        for entry in entries:
            if entry.data_offset >= len(data):
                continue
            block = data[entry.data_offset : min(len(data), entry.data_offset + 512 * 1024)]
            ps_runs = carve_mpegps_block(block) if entry.has_footage else []
            validation = "hikbtree_indexed" if entry.has_footage else "hikbtree_stale_entry"
            if not ps_runs and not entry.has_footage:
                ps_runs = carve_mpegps_block(block[:65536])
            for run in ps_runs or ([block[:65536]] if entry.has_footage else []):
                start_iso = _unix_iso(entry.start_unix)
                end_iso = _unix_iso(entry.end_unix)
                segments.append(
                    RecoveredSegment(
                        channel=entry.channel,
                        vendor=self.vendor,
                        offset_start=entry.data_offset,
                        offset_end=entry.data_offset + len(run),
                        frame_count=max(1, run.count(b"\x00\x00\x01\xba")),
                        confidence=0.9 if entry.has_footage else 0.55,
                        validation=validation,
                        raw_bytes=run,
                        codec="h264",
                        recorder_start_ts=start_iso,
                        recorder_end_ts=end_iso,
                        timestamp_source="hikbtree_entry" if start_iso else "unavailable",
                        timestamp_confidence=0.85 if start_iso else None,
                        parser_name=self.name,
                        parser_version=self.version,
                        signature_evidence={
                            "master_block": "HIKVISION@HANGZHOU",
                            "hikbtree_index": True,
                            "mpeg_ps_pack": b"\x00\x00\x01\xba" in run,
                        },
                        validation_evidence={
                            "hikbtree_stale": entry.stale,
                            "recovery_context": validation,
                        },
                    )
                )
        return _merge(segments)


def _unix_iso(value: int) -> str | None:
    if value <= 0 or value >= 0x7FFFFFFF:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _scan_legacy_hikvi(image_path: Path, *, max_bytes: int | None) -> list[RecoveredSegment]:
    """Fallback for old HKVI-shaped tier-1 bytes until fixtures are rebuilt."""
    from engine.app.parsers.schemas.hkvi import HKVI_MAGIC, validate_hkvi_block

    segments: list[RecoveredSegment] = []
    data = image_path.read_bytes() if max_bytes is None else image_path.read_bytes()[:max_bytes]
    offset = 0
    while offset + 32 < len(data):
        hit = data.find(HKVI_MAGIC, offset)
        if hit < 0:
            break
        parsed = validate_hkvi_block(data, hit)
        if parsed and parsed.checks.get("size_consistency"):
            segments.append(
                RecoveredSegment(
                    channel=parsed.channel,
                    vendor="Hikvision",
                    offset_start=hit,
                    offset_end=hit + parsed.block_len,
                    frame_count=1,
                    confidence=parsed.confidence,
                    validation=parsed.validation_level,
                    raw_bytes=data[hit : hit + parsed.block_len],
                    codec="h264",
                    recorder_start_ts=parsed.recorder_iso,
                    recorder_end_ts=parsed.recorder_iso,
                    timestamp_source="hkvi_block_epoch" if parsed.recorder_iso else "unavailable",
                    timestamp_confidence=0.8 if parsed.recorder_iso else None,
                    parser_name="hikvision",
                    parser_version="3-legacy",
                    signature_evidence={"block_header": "HKVI"},
                    validation_evidence=parsed.checks,
                )
            )
            offset = hit + parsed.block_len
        else:
            offset = hit + 4
    return segments


def _merge(segments: list[RecoveredSegment]) -> list[RecoveredSegment]:
    if not segments:
        return []
    segments.sort(key=lambda s: s.offset_start)
    out = [segments[0]]
    for seg in segments[1:]:
        prev = out[-1]
        if seg.offset_start <= prev.offset_end and seg.channel == prev.channel and seg.validation == prev.validation:
            out[-1] = RecoveredSegment(
                channel=prev.channel,
                vendor=prev.vendor,
                offset_start=prev.offset_start,
                offset_end=max(prev.offset_end, seg.offset_end),
                frame_count=prev.frame_count + seg.frame_count,
                confidence=min(prev.confidence, seg.confidence),
                validation=prev.validation,
                raw_bytes=b"",
                codec=prev.codec,
                recorder_start_ts=prev.recorder_start_ts,
                recorder_end_ts=seg.recorder_end_ts or prev.recorder_end_ts,
                timestamp_source=prev.timestamp_source,
                timestamp_confidence=prev.timestamp_confidence,
                parser_name=prev.parser_name,
                parser_version=prev.parser_version,
                signature_evidence=prev.signature_evidence,
                validation_evidence=prev.validation_evidence,
            )
        else:
            out.append(seg)
    return out
