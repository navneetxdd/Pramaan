from __future__ import annotations

import shutil
import subprocess
import tempfile
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


def _elementary_format(path: Path) -> str:
    """Demuxer name for a raw elementary stream by extension."""
    return "hevc" if path.suffix.lower() in {".h265", ".hevc", ".265"} else "h264"


def _prepare_playable_h264(source: Path) -> Path:
    """Copy the elementary stream to a temp file for ffmpeg.

    H.264 carves get SPS/PPS ensured (a carve can start mid-stream). HEVC and
    already-demuxed streams are copied verbatim — they carry their own parameter
    sets and the H.264 parameter-set prefix would corrupt an HEVC stream.
    """
    fmt = _elementary_format(source)
    suffix = f".playable.{ 'h265' if fmt == 'hevc' else 'h264' }"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        playable_path = Path(tmp.name)
    data = source.read_bytes()
    playable_path.write_bytes(data if fmt == "hevc" else ensure_playable_h264(data))
    return playable_path


def _probe_decodable(ffmpeg: str, playable_path: Path, *, timeout: float = 8.0) -> bool:
    """Fail fast (and never hang) on a carved range that isn't a real elementary stream.

    Carving only checks for one Annex-B start code near the carve point — it never
    guarantees the rest of the range decodes. Feeding that straight to a live transcode
    either exits instantly with zero bytes (looks like a broken empty video/mp4) or, for
    some malformed inputs, never exits at all. Confirmed against real (non-fixture) CCTV
    and phone footage. Probing one frame with a hard timeout catches both failure modes
    before any response has been sent, so the caller can return an honest error instead.

    Assumes the caller already verified ffmpeg is on PATH — this only judges the content.
    subprocess.run's own timeout handling kills and reaps the child for us, so a timeout
    here can't itself raise or leave a lingering process.
    """
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        _elementary_format(playable_path),
        "-i",
        str(playable_path),
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _ffmpeg_transcode_stream(ffmpeg: str, playable_path: Path, *, full: bool = False):
    try:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            _elementary_format(playable_path),
            "-i",
            str(playable_path),
        ]
        if not full:
            cmd.extend(["-vf", "scale='min(1280,iw)':-2"])
        cmd.extend(
            [
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
        )
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
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        playable_path.unlink(missing_ok=True)


@router.get("/{filename}", response_model=None)
def download_file(
    filename: str,
    transcode: int = Query(0, ge=0, le=1),
    full: int = Query(0, ge=0, le=1),
) -> Response:
    path = _resolve_export_path(filename)
    if transcode and path.suffix.lower() in {".h264", ".264", ".h265", ".hevc", ".265"}:
        ffmpeg = shutil.which(FFMPEG_BIN)
        if not ffmpeg:
            raise HTTPException(
                status_code=503,
                detail="FFmpeg is not installed on this workstation, so the raw "
                f"{_elementary_format(path).upper()} elementary stream cannot be "
                "remuxed for in-browser playback. Download the segment and open it "
                "in a local player (VLC, mpv), or install FFmpeg and retry.",
            )
        playable_path = _prepare_playable_h264(path)
        if not _probe_decodable(ffmpeg, playable_path):
            playable_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail="Recovered segment has no decodable video frames. The carved "
                "byte range is not a continuous, playable elementary stream.",
            )
        return StreamingResponse(
            _ffmpeg_transcode_stream(ffmpeg, playable_path, full=bool(full)),
            media_type="video/mp4",
            headers={"Cache-Control": "no-store"},
        )
    media = "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"
    if path.suffix.lower() in {".h264", ".264"}:
        media = "video/H264"
    elif path.suffix.lower() in {".h265", ".hevc", ".265"}:
        media = "video/H265"
    return FileResponse(path, filename=path.name, media_type=media)
