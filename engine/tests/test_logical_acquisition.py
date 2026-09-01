from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-logical-acq-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.services.logical_acquisition import LogicalClip, _session  # noqa: E402
from requests.auth import HTTPDigestAuth  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
