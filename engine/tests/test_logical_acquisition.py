from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlparse

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-logical-acq-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services.logical_acquisition import (  # noqa: E402
    LogicalClip,
    _hikvision_search_clips,
    _session,
)
from requests.auth import HTTPDigestAuth  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class _HikvisionIsapiHandler(BaseHTTPRequestHandler):
    clip_bytes: bytes = b"\x00\x00\x00\x01\x65" + b"\xab" * 256

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path.endswith("/ISAPI/ContentMgmt/search"):
            body = """<?xml version="1.0" encoding="UTF-8"?>
<CMSearchResult>
  <responseStatus>true</responseStatus>
  <responseStatusStrg>OK</responseStatusStrg>
  <numOfMatches>1</numOfMatches>
  <matchList>
    <searchMatchItem>
      <trackID>101</trackID>
      <timeSpan>
        <startTime>2020-01-01T00:00:00Z</startTime>
        <endTime>2020-01-01T00:01:00Z</endTime>
      </timeSpan>
      <mediaSegmentDescriptor>
        <playbackURI>rtsp://127.0.0.1/Streaming/tracks/101?starttime=20200101T000000Z</playbackURI>
      </mediaSegmentDescriptor>
    </searchMatchItem>
  </matchList>
</CMSearchResult>"""
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if "download" in self.path or "playbackURI" in self.path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.clip_bytes)
            return
        self.send_response(404)
        self.end_headers()


class LogicalAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def test_logical_hikvision_acquire_mock(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Logical acquire", "examiner_name": "Examiner"},
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]

        clip = LogicalClip(remote_path="/recordings/clip1.mp4", filename="clip1.mp4")
        payload = b"\x00\x00\x00\x01\x65" + b"\xab" * 128

        with (
            patch(
                "engine.app.services.logical_acquisition.discover_logical_clips",
                return_value=[clip],
            ),
            patch(
                "engine.app.services.logical_acquisition.download_logical_clip",
                return_value=payload,
            ),
        ):
            response = self.client.post(
                f"/api/v1/cases/{case_id}/devices/acquire/logical",
                json={
                    "actor": "Examiner",
                    "host": "192.168.1.64",
                    "port": 80,
                    "user": "admin",
                    "password": "secret",
                    "vendor": "hikvision",
                    "max_clips": 1,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["clips_acquired"], 1)
        device = body["devices"][0]["evidence"]
        self.assertTrue(device["sha256"])

        detail = self.client.get(f"/api/v1/devices/{device['id']}").json()
        self.assertEqual(detail["device"]["acquisition_method"], "logical_network")

    def test_logical_session_uses_digest_auth(self) -> None:
        session = _session("admin", "secret")
        self.assertIsInstance(session.auth, HTTPDigestAuth)

    def test_hikvision_isapi_search_finds_nested_playback_uri(self) -> None:
        handler = _HikvisionIsapiHandler
        handler.clip_bytes = b"\x00\x00\x00\x01\x65" + b"\xcd" * 128
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            session = _session("admin", "secret")
            clips = _hikvision_search_clips(
                session,
                scheme="http",
                host="127.0.0.1",
                port=port,
                user="admin",
                password="secret",
            )
            self.assertGreaterEqual(len(clips), 1)
            self.assertTrue(clips[0].remote_path.startswith("rtsp://"))
        finally:
            server.shutdown()

    def test_logical_hikvision_acquire_via_isapi_mock(self) -> None:
        handler = _HikvisionIsapiHandler
        handler.clip_bytes = b"\x00\x00\x00\x01\x65" + b"\xef" * 128
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            created = self.client.post(
                "/api/v1/cases",
                json={"name": "Hikvision ISAPI", "examiner_name": "Examiner"},
            )
            case_id = created.json()["id"]
            response = self.client.post(
                f"/api/v1/cases/{case_id}/devices/acquire/logical",
                json={
                    "actor": "Examiner",
                    "host": "127.0.0.1",
                    "port": port,
                    "user": "admin",
                    "password": "secret",
                    "vendor": "hikvision",
                    "max_clips": 1,
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertGreaterEqual(body["clips_acquired"], 1)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
