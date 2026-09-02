from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

import pytest

os.environ.setdefault("PRAMAAN_ALLOW_LOGICAL_ACQUIRE", "1")
os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="pramaan-live-int-"))

from fastapi.testclient import TestClient  # noqa: E402

from engine.app.core.config import CASES_DIR  # noqa: E402
from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services import live_devices  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _free_ports() -> tuple[int, int, int]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as rtsp_sock:
        rtsp_sock.bind(("127.0.0.1", 0))
        rtsp_port = int(rtsp_sock.getsockname()[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as rtp_sock:
        rtp_sock.bind(("127.0.0.1", 0))
        rtp_port = int(rtp_sock.getsockname()[1])
        if rtp_port % 2:
            rtp_port += 1
    return rtsp_port, rtp_port, rtp_port + 1


def _wait_for_rtsp(url: str, timeout_s: float = 45.0) -> None:
    if not shutil.which("ffprobe"):
        raise unittest.SkipTest("ffprobe required for integration test")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-rtsp_transport",
                "tcp",
                "-i",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        if probe.returncode == 0:
            return
        time.sleep(0.75)
    raise unittest.SkipTest(f"RTSP source not ready: {url}")


def _start_rtsp_publisher(path: str) -> tuple[int, subprocess.Popen[bytes], subprocess.Popen[bytes], Path]:
    if not shutil.which("ffmpeg"):
        raise unittest.SkipTest("ffmpeg required for integration test")
    rtsp_port, rtp_port, rtcp_port = _free_ports()
    cache = ROOT / ".localdata" / "dev" / "mediamtx"
    cache.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "rtsp_test_source",
        ROOT / "scripts" / "dev" / "rtsp_test_source.py",
    )
    if spec is None or spec.loader is None:
        raise unittest.SkipTest("rtsp_test_source helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mediamtx = module._download_mediamtx(cache)
    config_dir = Path(tempfile.mkdtemp(prefix="pramaan-mtx-"))
    config_path = config_dir / "mediamtx.yml"
    config_path.write_text(
        "\n".join(
            [
                f"rtspAddress: :{rtsp_port}",
                f"rtpAddress: :{rtp_port}",
                f"rtcpAddress: :{rtcp_port}",
                "rtmp: no",
                "hls: no",
                "webrtc: no",
                "srt: no",
                "paths:",
                f"  {path}:",
                "    source: publisher",
            ]
        ),
        encoding="ascii",
    )
    mtx = subprocess.Popen(
        [str(mediamtx), str(config_path)],
        cwd=str(cache),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    time.sleep(1.5)
    if mtx.poll() is not None:
        stderr = (mtx.stderr.read().decode("utf-8", errors="replace") if mtx.stderr else "").strip()
        raise unittest.SkipTest(f"mediamtx failed to start: {stderr or 'unknown error'}")
    publish_url = f"rtsp://127.0.0.1:{rtsp_port}/{path}"
    ffmpeg = subprocess.Popen(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "10",
            "-keyint_min",
            "10",
            "-bf",
            "0",
            "-c:a",
            "pcm_mulaw",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            publish_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_rtsp(publish_url)
    time.sleep(1.0)
    return rtsp_port, mtx, ffmpeg, config_dir


def _read_process_stdout(proc: subprocess.Popen[bytes], limit: int, timeout_s: float = 8.0) -> bytes:
    def _read() -> bytes:
        if not proc.stdout:
            return b""
        chunks: list[bytes] = []
        total = 0
        while total < limit:
            chunk = proc.stdout.read(min(4096, limit - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_read)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout:
            return b""
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)


@pytest.mark.integration
class LiveDevicesIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)
        cls.port, cls._mtx, cls._ffmpeg, cls._config_dir = _start_rtsp_publisher("cam1")
        cls.rtsp_url = f"rtsp://127.0.0.1:{cls.port}/cam1"

    @classmethod
    def tearDownClass(cls) -> None:
        for proc in (getattr(cls, "_ffmpeg", None), getattr(cls, "_mtx", None)):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        config_dir = getattr(cls, "_config_dir", None)
        if config_dir:
            shutil.rmtree(config_dir, ignore_errors=True)

    def test_mjpeg_mp4_and_capture_with_pcm_mulaw_audio(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Live integration", "examiner_name": "Examiner"},
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]
        add = self.client.post(
            f"/api/v1/cases/{case_id}/live-devices",
            json={
                "actor": "Examiner",
                "display_name": "Test cam",
                "vendor": "generic_rtsp",
                "host": "127.0.0.1",
                "port": self.port,
                "scheme": "rtsp",
                "user": "",
                "password": "",
                "rtsp_url_override": self.rtsp_url,
            },
        )
        self.assertEqual(add.status_code, 200, add.text)
        device_id = add.json()["id"]

        capture = self.client.post(
            f"/api/v1/live-devices/{device_id}/capture",
            json={"actor": "Examiner", "channel": 1, "duration_s": 2},
            timeout=30.0,
        )
        self.assertEqual(capture.status_code, 200, capture.text)
        capture_body = capture.json()
        clip = CASES_DIR / case_id / "live" / capture_body["evidence"]["filename"]
        self.assertTrue(clip.exists(), f"missing capture artifact: {clip}")
        self.assertGreater(clip.stat().st_size, 1000)
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(clip),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn("h264", probe.stdout)

        mjpeg_proc = live_devices.mjpeg_stream(device_id, 1, fps=4)
        mjpeg_body = _read_process_stdout(mjpeg_proc, 8192)
        self.assertIn(b"\xff\xd8", mjpeg_body)
        self.assertGreater(len(mjpeg_body), 1000)

        mp4_proc = live_devices.mp4_stream(device_id, 1)
        mp4_body = _read_process_stdout(mp4_proc, 4096)
        self.assertGreater(len(mp4_body), 100)
        self.assertTrue(b"ftyp" in mp4_body or b"moov" in mp4_body)


if __name__ == "__main__":
    unittest.main()
