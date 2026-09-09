from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.unwrap import unwrap_to_h264
from engine.app.verification.builder_specimen import build_dahua_builder_specimen
from engine.app.verification.media_fixture import split_annexb_nals


def _nal_header_byte(nal: bytes) -> int | None:
    if nal.startswith(b"\x00\x00\x00\x01") and len(nal) > 4:
        return nal[4]
    if nal.startswith(b"\x00\x00\x01") and len(nal) > 3:
        return nal[3]
    return None


def _nal_types(h264: bytes) -> set[int]:
    types: set[int] = set()
    for nal in split_annexb_nals(h264):
        b0 = _nal_header_byte(nal)
        if b0 is not None:
            types.add(b0 & 0x1F)
    return types


def _has_video_slices(stream: bytes) -> bool:
    """True when the elementary stream carries at least one coded picture,
    for either H.264 (NAL types 1/5) or HEVC (VCL NAL types 0-31)."""
    for nal in split_annexb_nals(stream):
        b0 = _nal_header_byte(nal)
        if b0 is None:
            continue
        if (b0 & 0x1F) in (1, 5):  # H.264 non-IDR / IDR slice
            return True
        if (b0 & 0x80) == 0 and ((b0 >> 1) & 0x3F) <= 31:  # HEVC VCL NAL
            return True
    return False


def _playable_export_stage(device_id: str, sequences: list[dict]) -> dict:
    if not sequences:
        return {"stage": "dahua_playable_export", "passed": False, "detail": "no sequences"}
    first = sequences[0]
    output_path = first.get("output_path")
    if not output_path:
        return {"stage": "dahua_playable_export", "passed": False, "detail": "missing output_path"}
    path = Path(output_path)
    if not path.is_file():
        return {"stage": "dahua_playable_export", "passed": False, "detail": "artifact missing"}
    stream = unwrap_to_h264(path.read_bytes())
    types = _nal_types(stream)
    playable = _has_video_slices(stream)
    return {
        "stage": "dahua_playable_export",
        "passed": playable,
        "detail": f"nal_types={sorted(types)} bytes={path.stat().st_size}",
    }


def dahua_real_dav_stage(path: Path) -> dict:
    if not path.is_file():
        return {"stage": "dahua_real_dav_parse", "passed": True, "detail": "skipped (asset absent)"}
    segments = DahuaDhavAdapter().scan(path)
    total_frames = sum(int(s.frame_count or 0) for s in segments)
    if total_frames < 10:
        return {
            "stage": "dahua_real_dav_parse",
            "passed": False,
            "detail": f"only {total_frames} frames across {len(segments)} segment(s)",
        }
    chunk = path.read_bytes()[segments[0].offset_start : segments[0].offset_end]
    stream = unwrap_to_h264(chunk)
    if not _has_video_slices(stream):
        return {"stage": "dahua_real_dav_parse", "passed": False, "detail": "no slice/IDR in first segment"}
    return {
        "stage": "dahua_real_dav_parse",
        "passed": True,
        "detail": f"{total_frames} frames across {len(segments)} segment(s) from real .dav",
    }
