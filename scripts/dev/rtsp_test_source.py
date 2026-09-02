#!/usr/bin/env python3
"""Start a local RTSP test source for live-device PoC (mediamtx + ffmpeg loop)."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIAMTX_VERSION = "1.9.3"

MEDIAMTX_URLS = {
    "Windows": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_windows_amd64.zip",
    "Linux": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_linux_amd64.tar.gz",
    "Darwin": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_darwin_amd64.tar.gz",
}


def _download_mediamtx(dest: Path) -> Path:
    system = platform.system()
    url = MEDIAMTX_URLS.get(system)
    if not url:
        raise RuntimeError(f"Unsupported platform for mediamtx bootstrap: {system}")
    archive = dest / Path(url).name
    if not archive.exists():
        print(f"Downloading mediamtx from {url}")
        urllib.request.urlretrieve(url, archive)
    bin_name = "mediamtx.exe" if system == "Windows" else "mediamtx"
    binary = dest / bin_name
    if binary.exists():
        return binary
    if archive.suffix == ".zip":
        import zipfile

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    else:
        import tarfile

        with tarfile.open(archive) as tf:
            tf.extractall(dest)
    if not binary.exists():
        raise RuntimeError(f"mediamtx binary not found after extracting {archive}")
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8554, help="RTSP listen port")
    parser.add_argument("--path", default="live", help="RTSP path name")
    parser.add_argument(
        "--source",
        default=str(ROOT / "validation_data" / "fixtures" / "caviar" / "logical_clip1.mp4"),
        help="Looping MP4/H264 file to publish",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg is required on PATH", file=sys.stderr)
        return 1

    source = Path(args.source)
    if not source.exists():
        print(f"Source file not found: {source}", file=sys.stderr)
        return 1

    cache = ROOT / ".localdata" / "dev" / "mediamtx"
    cache.mkdir(parents=True, exist_ok=True)
    mediamtx = _download_mediamtx(cache)

    config = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8")
    config.write(
        f"""
rtspAddress: :{args.port}
paths:
  {args.path}:
    source: publisher
""".strip()
    )
    config.flush()
    config_path = config.name

    mtx = subprocess.Popen([str(mediamtx), config_path], cwd=str(cache))
    time.sleep(1.5)

    publish_url = f"rtsp://127.0.0.1:{args.port}/{args.path}"
    ffmpeg_cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop",
        "-1",
        "-i",
        str(source),
        "-c",
        "copy",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        publish_url,
    ]
    print(f"Publishing {source} → {publish_url}")
    print("Use rtsp://127.0.0.1:{port}/{path} in Live devices (generic RTSP vendor).".format(
        port=args.port,
        path=args.path,
    ))
    try:
        subprocess.run(ffmpeg_cmd, check=False)
    finally:
        mtx.terminate()
        mtx.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
