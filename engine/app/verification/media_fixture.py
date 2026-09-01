"""Real decodable H.264 Annex-B payloads for lab specimens (CAVIAR Walk1)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from engine.app.core.config import FFMPEG_BIN, VALIDATION_DATA_DIR
from engine.app.parsers.unwrap import NAL_START_4

CAVIAR_MPG = VALIDATION_DATA_DIR / "external" / "caviar" / "Walk1.mpg"
H264_FALLBACK = VALIDATION_DATA_DIR / "fixtures" / "media" / "caviar_walk1_320x240.h264"

_annexb_cache: bytes | None = None
_nal_cache: list[bytes] | None = None


def _ffmpeg_bin() -> str | None:
    if shutil.which(FFMPEG_BIN):
        return FFMPEG_BIN
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _transcode_caviar(max_frames: int) -> bytes:
    ffmpeg = _ffmpeg_bin()
    if ffmpeg is None:
        raise RuntimeError("ffmpeg unavailable for CAVIAR transcode")
    if not CAVIAR_MPG.is_file():
        raise FileNotFoundError(f"CAVIAR source missing: {CAVIAR_MPG}")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(CAVIAR_MPG),
        "-vf",
        "scale=320:240",
        "-r",
        "6",
        "-frames:v",
        str(max_frames),
        "-c:v",
        "libx264",
        "-profile:v",
        "baseline",
        "-bsf:v",
        "h264_mp4toannexb",
        "-f",
        "h264",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True)
    if not proc.stdout.startswith(NAL_START_4):
        raise RuntimeError("CAVIAR transcode did not produce Annex-B H.264")
    return proc.stdout


def caviar_h264_annexb(max_frames: int = 120) -> bytes:
    """Return Annex-B H.264 bytes from CAVIAR Walk1 (transcoded or committed fallback)."""
    global _annexb_cache
    if _annexb_cache is not None:
        return _annexb_cache

    if H264_FALLBACK.is_file():
        _annexb_cache = H264_FALLBACK.read_bytes()
        return _annexb_cache

    try:
        _annexb_cache = _transcode_caviar(max_frames)
    except Exception:
        if H264_FALLBACK.is_file():
            _annexb_cache = H264_FALLBACK.read_bytes()
        else:
            raise
    return _annexb_cache


def split_annexb_nals(data: bytes) -> list[bytes]:
    """Split Annex-B stream into NAL units (each includes the start code prefix)."""
    if not data:
        return []
    starts: list[int] = []
    idx = 0
    while idx < len(data) - 3:
        if data[idx : idx + 4] == NAL_START_4:
            starts.append(idx)
            idx += 4
        elif data[idx : idx + 3] == b"\x00\x00\x01":
            starts.append(idx)
            idx += 3
        else:
            idx += 1
    if not starts:
        return [data]
    nals: list[bytes] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(data)
        nals.append(data[start:end])
    return nals


def caviar_nal_units() -> list[bytes]:
    global _nal_cache
    if _nal_cache is None:
        _nal_cache = split_annexb_nals(caviar_h264_annexb())
    return _nal_cache


class NalPayloadSource:
    """Round-robin whole-NAL payloads for specimen builders."""

    def __init__(self) -> None:
        self._nals = caviar_nal_units()
        if not self._nals:
            raise RuntimeError("CAVIAR NAL split produced no units")
        self._cursor = 0

    def next_payload(self, min_len: int) -> bytes:
        if min_len <= 0:
            raise ValueError("min_len must be positive")
        parts: list[bytes] = []
        total = 0
        guard = 0
        while total < min_len and guard < len(self._nals) * 4:
            nal = self._nals[self._cursor % len(self._nals)]
            self._cursor += 1
            parts.append(nal)
            total += len(nal)
            guard += 1
        payload = b"".join(parts)
        if len(payload) < min_len:
            payload += b"\x00" * (min_len - len(payload))
        return payload

    def next_single_nal(self) -> bytes:
        nal = self._nals[self._cursor % len(self._nals)]
        self._cursor += 1
        return nal
