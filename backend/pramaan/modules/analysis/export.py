from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from pramaan.config import EXPORTS_DIR, FFMPEG_BIN
from pramaan.modules.analysis.unwrap import NAL_START_3, NAL_START_4, unwrap_to_h264


def export_segment(
    image_path: Path,
    offset_start: int,
    offset_end: int,
    vendor: str,
    out_dir: Path | None = None,
) -> Path:
    out_dir = out_dir or EXPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{uuid.uuid4().hex}.h264"
    mp4_path = out_dir / f"{raw_path.stem}.mp4"

    with image_path.open("rb") as src:
        src.seek(offset_start)
        chunk = src.read(offset_end - offset_start)

    h264_bytes = unwrap_to_h264(chunk) if vendor.lower().startswith("dahua") else chunk
    if NAL_START_3 not in h264_bytes and NAL_START_4 not in h264_bytes:
        h264_bytes = unwrap_to_h264(chunk)

    raw_path.write_bytes(h264_bytes)

    if shutil.which(FFMPEG_BIN):
        cmd = [
            FFMPEG_BIN,
            "-y",
            "-f",
            "h264",
            "-i",
            str(raw_path),
            "-c",
            "copy",
            str(mp4_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and mp4_path.exists():
            raw_path.unlink(missing_ok=True)
            return mp4_path

    return raw_path
