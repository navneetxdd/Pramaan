from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from pramaan.config import EXPORTS_DIR, FFMPEG_BIN


def export_segment_h264(image_path: Path, offset_start: int, offset_end: int, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or EXPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{uuid.uuid4().hex}.h264"
    mp4_path = out_dir / f"{raw_path.stem}.mp4"

    with image_path.open("rb") as src, raw_path.open("wb") as dst:
        src.seek(offset_start)
        dst.write(src.read(offset_end - offset_start))

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


def build_case_report(case: dict, evidence: list[dict], jobs: list[dict], custody: list[dict]) -> dict:
    return {
        "case": case,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "recovery_jobs": jobs,
        "custody_events": custody,
        "generated_by": "Pramaan",
    }
