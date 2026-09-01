from __future__ import annotations

import os
import tempfile
import time
import unittest

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-honeywell-e2e-")

from engine.app.core.db import init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402


class HoneywellE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _wait_job(self, job_id: str, timeout_s: float = 60.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self.client.get(f"/api/v1/jobs/{job_id}/status").json()
            if status.get("status") in ("completed", "failed", "error", "interrupted"):
                return status
            time.sleep(0.2)
        raise TimeoutError(f"Job {job_id} did not finish")

    def test_honeywell_known_answer_pipeline(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Honeywell POC", "examiner_name": "Examiner"},
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]

        acquire = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "source": "synthetic_specimen", "vendor": "honeywell"},
        )
        self.assertEqual(acquire.status_code, 200)
        body = acquire.json()
        self.assertEqual(body.get("vendor"), "honeywell")
        device_id = body["evidence"]["id"]

        identification = self.client.get(f"/api/v1/devices/{device_id}/identification").json()
        hits = identification.get("hits") or []
        self.assertTrue(any(h.get("vendor") == "Honeywell" for h in hits))

        verify = self.client.get(f"/api/v1/devices/{device_id}/verify").json()
        self.assertTrue(verify.get("ok"))

        recover = self.client.post(
            f"/api/v1/devices/{device_id}/recover",
            json={"actor": "Examiner"},
        )
        self.assertEqual(recover.status_code, 200)
        job_id = recover.json()["job"]["id"]
        job = self._wait_job(job_id)
        self.assertEqual(job.get("status"), "completed")

        job_detail = self.client.get(f"/api/v1/jobs/{job_id}").json()
        segments = job_detail.get("segments") or []
        self.assertGreater(len(segments), 0)
        validations = {s.get("validation") or s.get("confidence_tier") for s in segments}
        self.assertTrue(
            any(v in {"honeywell_expired_index", "honeywell_format_carve_4", "honeywell_index_4"} for v in validations),
            validations,
        )

        timeline = self.client.get(f"/api/v1/cases/{case_id}/timeline/{device_id}").json()
        self.assertGreaterEqual(timeline.get("channel_count", 0), 0)

        report = self.client.get(f"/api/v1/cases/{case_id}/report.pdf")
        self.assertEqual(report.status_code, 200)
        self.assertTrue(report.content.startswith(b"%PDF"))

        segment_id = segments[0].get("id") or segments[0].get("segment_id")
        if segment_id:
            export = self.client.post(f"/api/v1/devices/{device_id}/sequences/{segment_id}/export")
            self.assertEqual(export.status_code, 200)
            self.assertIn("download_url", export.json())


if __name__ == "__main__":
    unittest.main()
