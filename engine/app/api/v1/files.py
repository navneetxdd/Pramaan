from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse

from engine.app.core.config import EXPORTS_DIR, FFMPEG_BIN
from engine.app.verification.media_fixture import ensure_playable_h264

router = APIRouter(prefix="/files", tags=["files"])


def _resolve_export_path(filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (EXPORTS_DIR / filename).resolve()
    if not str(path).startswith(str(EXPORTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    return path


def _ffmpeg_transcode_stream(source: Path):
    ffmpeg = shutil.which(FFMPEG_BIN)
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="FFmpeg not available for inline playback")
    playable = EXPORTS_DIR / f"{source.stem}.playable.h264"
    playable.write_bytes(ensure_playable_h264(source.read_bytes()))
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "h264",
        "-i",
        str(playable),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-f",
        "mp4",
        "-movflags",
        "frag_keyframe+empty_moov",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not proc.stdout:
        raise HTTPException(status_code=500, detail="FFmpeg transcode pipe failed")
    try:
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        proc.stdout.close()
        proc.wait(timeout=5)


@router.get("/{filename}", response_model=None)
def download_file(
    filename: str,
    transcode: int = Query(0, ge=0, le=1),
) -> Response:
    path = _resolve_export_path(filename)
    if transcode and path.suffix.lower() in {".h264", ".264"}:
        return StreamingResponse(
            _ffmpeg_transcode_stream(path),
            media_type="video/mp4",
            headers={"Cache-Control": "no-store"},
        )
    media = "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"
    if path.suffix.lower() in {".h264", ".264"}:
        media = "video/H264"
    return FileResponse(path, filename=path.name, media_type=media)
