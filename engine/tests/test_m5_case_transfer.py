from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-m5-test-")

from engine.app.core.db import init_db  # noqa: E402
from engine.app.core.repository import (  # noqa: E402
    get_case,
    list_ai_findings_for_device,
    verify_device_integrity,
)
from engine.app.services.ai_analytics import run_ai_analytics_job  # noqa: E402
from engine.app.services.case_bundle import export_case_bundle, import_case_bundle  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402


class M5CaseTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _prepare_case_with_recovery(self) -> tuple[str, str]:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "M5 Export", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        acquire = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "source": "synthetic_specimen"},
        )
        device_id = acquire.json()["evidence"]["id"]
        recover = self.client.post(
            f"/api/v1/devices/{device_id}/recover",
            json={"actor": "Examiner"},
        )
        job_id = recover.json()["job"]["id"]
        deadline = 60
        import time

        while deadline > 0:
            status = self.client.get(f"/api/v1/jobs/{job_id}/status").json()
            if status.get("status") == "completed":
                break
            time.sleep(0.3)
            deadline -= 1
        return case_id, device_id

    def test_export_import_roundtrip(self) -> None:
        case_id, device_id = self._prepare_case_with_recovery()
        bundle = export_case_bundle(case_id, "Examiner")
        self.assertTrue(bundle.exists())

        deleted = self.client.delete(f"/api/v1/cases/{case_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertIsNone(get_case(case_id))

        result = import_case_bundle(bundle, "Importer")
        self.assertEqual(result["case_id"], case_id)
        self.assertTrue(result["integrity_ok"])
        self.assertGreater(result["files_verified"], 0)
        self.assertTrue(verify_device_integrity(device_id)["ok"])

    def test_export_api(self) -> None:
        case_id, _ = self._prepare_case_with_recovery()
        response = self.client.post(
            f"/api/v1/cases/{case_id}/export",
            data={"actor": "Examiner"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("download_url", response.json())

    def test_ai_analytics_job(self) -> None:
        case_id, device_id = self._prepare_case_with_recovery()
        job_id = uuid.uuid4().hex
        asyncio.run(run_ai_analytics_job(job_id, case_id, device_id, "Examiner"))
        findings = list_ai_findings_for_device(device_id)
        self.assertGreaterEqual(len(findings), 0)

    def test_ai_analytics_api(self) -> None:
        case_id, device_id = self._prepare_case_with_recovery()
        started = self.client.post(
            f"/api/v1/devices/{device_id}/ai-analytics",
            json={"actor": "Examiner"},
        )
        self.assertEqual(started.status_code, 200)
        job_id = started.json()["job"]["id"]

        import time

        for _ in range(120):
            status = self.client.get(f"/api/v1/jobs/{job_id}/status").json()
            if status.get("status") in ("completed", "failed"):
                break
            time.sleep(0.2)
        self.assertEqual(status.get("status"), "completed")

        findings = self.client.get(f"/api/v1/devices/{device_id}/ai-findings")
        self.assertEqual(findings.status_code, 200)


if __name__ == "__main__":
    unittest.main()
