#!/usr/bin/env python3
"""Native desktop launcher — SAC-safe path without Rust release builds."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE_URL = os.environ.get("PRAMAAN_ENGINE_URL", "http://127.0.0.1:8787")
DEFAULT_UI_URL = os.environ.get("PRAMAAN_UI_URL", "http://127.0.0.1:5173")
VERSION_URL = f"{ENGINE_URL.rstrip('/')}/api/v1/version"


class _UiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def start_engine() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(ROOT / "run.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_static_ui(dist_dir: Path, port: int) -> ThreadingHTTPServer:
    handler = lambda *args, **kwargs: _UiHandler(  # noqa: E731
        *args, directory=str(dist_dir), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_for_url(url: str, timeout_s: float = 25.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.35)
    return False


def run_desktop(ui_url: str) -> int:
    try:
        import webview
    except ImportError:
        print("Missing dependency. Install with: pip install -r requirements-desktop.txt")
        return 1

    engine = start_engine()
    if not wait_for_url(VERSION_URL):
        print(f"Forensic engine did not start on {ENGINE_URL}")
        engine.terminate()
        return 1

    def on_closed() -> None:
        engine.terminate()
        try:
            engine.wait(timeout=5)
        except subprocess.TimeoutExpired:
            engine.kill()

    window = webview.create_window(
        "Pramaan",
        ui_url,
        width=1440,
        height=920,
        min_size=(1100, 680),
        background_color="#070b12",
    )

    def watch_engine() -> None:
        while True:
            if engine.poll() is not None:
                try:
                    webview.windows[0].destroy()
                except Exception:
                    pass
                break
            time.sleep(1.0)

    threading.Thread(target=watch_engine, daemon=True).start()

    try:
        webview.start(on_closed)
    finally:
        if engine.poll() is None:
            engine.terminate()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Pramaan desktop shell without Tauri release build")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Serve built dist/ on port 5174 (run npm run build first)",
    )
    parser.add_argument("--ui-url", default=DEFAULT_UI_URL, help="UI URL when not using --production")
    args = parser.parse_args()

    ui_url = args.ui_url
    static_server: ThreadingHTTPServer | None = None
    if args.production:
        dist = ROOT / "dist"
        if not (dist / "index.html").exists():
            print("dist/index.html missing. Run: npm run build")
            return 1
        static_server = start_static_ui(dist, 5174)
        ui_url = "http://127.0.0.1:5174"
        if not wait_for_url(ui_url):
            print("Static UI server failed to start on port 5174")
            if static_server:
                static_server.shutdown()
            return 1

    try:
        return run_desktop(ui_url)
    finally:
        if static_server:
            static_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
