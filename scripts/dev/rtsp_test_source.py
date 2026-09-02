#!/usr/bin/env python3
"""Start mediamtx + ffmpeg RTSP publishers for live-device PoC (Windows-first)."""

from __future__ import annotations

import argparse
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIAMTX_VERSION = "1.9.3"
CONFIG = Path(__file__).resolve().parent / "mediamtx.yml"
OEM = ROOT / "validation_data" / "oem"

MEDIAMTX_URLS = {
    "Windows": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_windows_amd64.zip",
    "Linux": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_linux_amd64.tar.gz",
    "Darwin": f"https://github.com/bluenviron/mediamtx/releases/download/v{MEDIAMTX_VERSION}/mediamtx_v{MEDIAMTX_VERSION}_darwin_amd64.tar.gz",
}

SOURCES = {
    "cam1": OEM / "hikvision_NVR_Camera01.mp4",
    "cam2": OEM / "hikvision_ch01_20090329.mp4",
    "cam3": OEM / "cam3_from_dahua.mp4",
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


def _ensure_cam3() -> Path:
    dest = SOURCES["cam3"]
    if dest.exists():
        return dest
    dav = OEM / "dahua_19.25.00-19.25.50-R.dav"
    if not dav.exists():
        print(
            "Missing cam3 transcode source. Place dahua_19.25.00-19.25.50-R.dav in validation_data/oem/",
            file=sys.stderr,
        )
        sys.exit(1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(dav),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not dest.exists():
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(1)
    return dest


def _publishers(port: int) -> list[tuple[str, Path]]:
    missing = [name for name, path in SOURCES.items() if name != "cam3" and not path.exists()]
    if missing:
        print(
            "Missing OEM samples for: "
            + ", ".join(missing)
            + ". Fetch real files into validation_data/oem/ first.",
            file=sys.stderr,
        )
        sys.exit(1)
    _ensure_cam3()
    return [(name, path) for name, path in SOURCES.items()]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8554)
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg is required on PATH", file=sys.stderr)
        return 1

    cache = ROOT / ".localdata" / "dev" / "mediamtx"
    cache.mkdir(parents=True, exist_ok=True)
    mediamtx = _download_mediamtx(cache)

    mtx = subprocess.Popen([str(mediamtx), str(CONFIG)], cwd=str(cache))
    time.sleep(1.5)

    children: list[subprocess.Popen[bytes]] = []

    def _shutdown(*_args: object) -> None:
        for child in children:
            child.terminate()
        mtx.terminate()
        for child in children:
            child.wait(timeout=5)
        mtx.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    for path_name, source in _publishers(args.port):
        url = f"rtsp://127.0.0.1:{args.port}/{path_name}"
        cmd = [
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
            url,
        ]
        children.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        print(f"Publishing {source.name} -> {url}")

    print("RTSP test sources running. Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
