from __future__ import annotations

import os
import tempfile
import time
import unittest

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-caviar-ai-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.services.ai_analytics import _load_cv  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402


class CaviarAnalyticsE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _wait_job(self, job_id: str, timeout_s: float = 90.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self.client.get(f"/api/v1/jobs/{job_id}/status").json()
            if status.get("status") in ("completed", "failed", "error", "interrupted"):
                return status
            time.sleep(0.2)
        raise TimeoutError(f"Job {job_id} did not finish")

    def test_honeywell_recovery_produces_analytics_leads(self) -> None:
        if not _load_cv():
            self.skipTest("OpenCV unavailable on this host")

        created = self.client.post(
            "/api/v1/cases",
            json={"name": "CAVIAR analytics", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        acquire = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "source": "synthetic_specimen", "vendor": "honeywell"},
        )
        device_id = acquire.json()["evidence"]["id"]
        recover = self.client.post(f"/api/v1/devices/{device_id}/recover", json={"actor": "Examiner"})
        job = self._wait_job(recover.json()["job"]["id"])
        self.assertEqual(job.get("status"), "completed")

        analytics = self.client.post(f"/api/v1/devices/{device_id}/ai-analytics", json={"actor": "Examiner"})
        self.assertEqual(analytics.status_code, 200)
        analytics_job = self._wait_job(analytics.json()["job"]["id"])
        self.assertEqual(analytics_job.get("status"), "completed")

        findings = self.client.get(f"/api/v1/devices/{device_id}/ai-findings").json()["findings"]
        actionable = [
            finding
            for finding in findings
            if finding["finding_type"] in {"object", "motion", "scene_change", "face"}
            and finding.get("bbox")
        ]
        self.assertGreaterEqual(len(actionable), 1)
        sample = actionable[0]
        self.assertIn("detector", sample["bbox"])


if __name__ == "__main__":
    unittest.main()
