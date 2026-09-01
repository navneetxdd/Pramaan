from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.unwrap import unwrap_to_h264
from engine.app.verification.lab_specimen import build_dahua_lab_specimen
from engine.app.verification.media_fixture import split_annexb_nals


def _nal_types(h264: bytes) -> set[int]:
    types: set[int] = set()
    for nal in split_annexb_nals(h264):
        if nal.startswith(b"\x00\x00\x00\x01") and len(nal) > 4:
            types.add(nal[4] & 0x1F)
        elif nal.startswith(b"\x00\x00\x01") and len(nal) > 3:
            types.add(nal[3] & 0x1F)
    return types


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
    h264 = unwrap_to_h264(path.read_bytes())
    types = _nal_types(h264)
    playable = bool(types & {1, 5})
    return {
        "stage": "dahua_playable_export",
        "passed": playable,
        "detail": f"nal_types={sorted(types)} bytes={path.stat().st_size}",
    }


def dahua_real_dav_stage(path: Path) -> dict:
    if not path.is_file():
        return {"stage": "dahua_real_dav_parse", "passed": True, "detail": "skipped (asset absent)"}
    segments = DahuaDhavAdapter().scan(path)
    if len(segments) < 10:
        return {
            "stage": "dahua_real_dav_parse",
            "passed": False,
            "detail": f"only {len(segments)} segments",
        }
    chunk = path.read_bytes()[segments[0].offset_start : segments[0].offset_end]
    h264 = unwrap_to_h264(chunk)
    if not (_nal_types(h264) & {1, 5}):
        return {"stage": "dahua_real_dav_parse", "passed": False, "detail": "no slice/IDR in first segment"}
    return {
        "stage": "dahua_real_dav_parse",
        "passed": True,
        "detail": f"{len(segments)} segments from real .dav",
    }
