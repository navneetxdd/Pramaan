from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-dahua-mock-"))

from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services.logical_acquisition import acquire_logical_network  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

REAL_DAV_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "validation_data" / "oem" / "dahua_19.25.00-19.25.50-R.dav",
    Path(r"C:\Users\navne\Downloads\pramaan-real-data\dahua_19.25.00-19.25.50-R.dav"),
)


def _resolve_real_dav() -> Path | None:
    for candidate in REAL_DAV_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


class _DahuaDigestHandler(BaseHTTPRequestHandler):
    dav_bytes: bytes = b""
    remote_path: str = "/mnt/sd/dahua_19.25.00-19.25.50-R.dav"
    _served_clip: bool = False

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_text(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/cgi-bin/mediaFileFind.cgi":
            if "factory.create" in parsed.query:
                type(self)._served_clip = False
                body = "result=mock-object-1\n"
            elif "findFile" in parsed.query:
                body = "found=1\n"
            elif "findNextFile" in parsed.query:
                if not getattr(self, "_served_clip", False):
                    self._served_clip = True
                    body = f"items[0].Path={self.remote_path}\n"
                else:
                    body = "found=0\n"
            elif "close" in parsed.query or "destroy" in parsed.query:
                body = "OK\n"
            else:
                body = "OK\n"
            self._send_text(body)
            return
        if parsed.path.startswith("/cgi-bin/RPC_Loadfile"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(self.dav_bytes)))
            self.end_headers()
            self.wfile.write(self.dav_bytes)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


class LogicalDahuaMockTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dav_path = _resolve_real_dav()
        if cls.dav_path is None:
            raise unittest.SkipTest("real Dahua .dav sample not staged")
        init_db()
        cls.client = TestClient(app)

    async def test_acquire_logical_network_downloads_hash_identical_dav(self) -> None:
        dav_bytes = self.dav_path.read_bytes()
        expected_sha = hashlib.sha256(dav_bytes).hexdigest()
        handler = _DahuaDigestHandler
        handler.dav_bytes = dav_bytes
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            created = self.client.post(
                "/api/v1/cases",
                json={"name": "Dahua mock", "examiner_name": "Examiner"},
            )
            case_id = created.json()["id"]
            result = await acquire_logical_network(
                case_id,
                "Examiner",
                host="127.0.0.1",
                port=port,
                user="admin",
                password="secret",
                vendor="dahua",
                scheme="http",
                max_clips=1,
            )
            self.assertEqual(result["clips_acquired"], 1)
            device_sha = result["devices"][0]["evidence"]["sha256"]
            self.assertEqual(device_sha, expected_sha)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
