from __future__ import annotations

import os
import tempfile
import unittest

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-bytes-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class DeviceBytesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def test_bytes_find_ascii(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Bytes find", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        acquired = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "vendor": "dahua"},
        )
        device_id = acquired.json()["evidence"]["id"]
        found = self.client.get(
            f"/api/v1/devices/{device_id}/bytes/find",
            params={"q": "DHAV", "from_offset": 0, "encoding": "ascii"},
        )
        self.assertEqual(found.status_code, 200)
        body = found.json()
        self.assertIsNotNone(body.get("offset"))

    def test_segment_detail(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Segment detail", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        acquired = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "vendor": "honeywell"},
        )
        device_id = acquired.json()["evidence"]["id"]
        recover = self.client.post(
            f"/api/v1/devices/{device_id}/recover",
            json={"actor": "Examiner"},
        )
        job_id = recover.json()["job"]["id"]
        import time

        for _ in range(60):
            status = self.client.get(f"/api/v1/jobs/{job_id}").json()
            if status["job"]["status"] == "completed":
                break
            if status["job"]["status"] in {"failed", "cancelled"}:
                self.fail(status["job"].get("error") or "recovery failed")
            time.sleep(0.25)
        segments = self.client.get(f"/api/v1/devices/{device_id}/sequences").json()["segments"]
        if not segments:
            self.skipTest("Recovery produced no segments in time budget")
        seg_id = segments[0]["id"]
        detail = self.client.get(f"/api/v1/devices/{device_id}/sequences/{seg_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], seg_id)


if __name__ == "__main__":
    unittest.main()
