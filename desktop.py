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


def open_system_browser(url: str) -> None:
    import webbrowser

    webbrowser.open(url, new=1)


def run_browser_shell(ui_url: str, engine: subprocess.Popen[bytes]) -> int:
    print(f"Pramaan running in your default browser: {ui_url}")
    print(f"Forensic engine: {ENGINE_URL}")
    print("Close this window or press Ctrl+C to stop the engine.")
    open_system_browser(ui_url)
    try:
        engine.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if engine.poll() is None:
            engine.terminate()
            try:
                engine.wait(timeout=5)
            except subprocess.TimeoutExpired:
                engine.kill()
    return 0


def run_desktop(ui_url: str, *, force_browser: bool = False) -> int:
    engine = start_engine()
    if not wait_for_url(VERSION_URL):
        print(f"Forensic engine did not start on {ENGINE_URL}")
        engine.terminate()
        return 1

    if force_browser:
        return run_browser_shell(ui_url, engine)

    try:
        import webview
    except ImportError:
        print("pywebview not installed — opening the system browser instead.")
        print("Install desktop deps with: pip install -r requirements-desktop.txt")
        return run_browser_shell(ui_url, engine)

    loaded = threading.Event()

    def on_closed() -> None:
        engine.terminate()
        try:
            engine.wait(timeout=5)
        except subprocess.TimeoutExpired:
            engine.kill()

    def on_loaded() -> None:
        loaded.set()

    window = webview.create_window(
        "Pramaan",
        ui_url,
        width=1440,
        height=920,
        min_size=(1100, 680),
        background_color="#070b12",
    )
    window.events.loaded += on_loaded

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
        webview.start(on_closed, gui="edgechromium")
    except Exception as exc:
        print(f"WebView2 failed to start ({exc}). Opening the system browser instead.")
        return run_browser_shell(ui_url, engine)

    if not loaded.is_set():
        print(
            "WebView2 did not initialize (common on some Windows builds). "
            "Opening the system browser instead.\n"
            "For a native window with icon, install: release-artifacts\\nsis\\Pramaan_0.6.0_x64-setup.exe"
        )
        return run_browser_shell(ui_url, engine)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Pramaan desktop shell without Tauri release build")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Serve built dist/ on port 5174 (run npm run build first)",
    )
    parser.add_argument("--ui-url", default=DEFAULT_UI_URL, help="UI URL when not using --production")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Skip pywebview and open the UI in the system browser",
    )
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
        return run_desktop(ui_url, force_browser=args.browser)
    finally:
        if static_server:
            static_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
