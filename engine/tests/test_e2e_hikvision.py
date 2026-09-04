from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-hikvision-e2e-")

from engine.app.core.db import init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402
from engine.app.core.repository import get_device, list_sequences  # noqa: E402


class HikvisionE2ETests(unittest.TestCase):
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

    def test_hikvision_known_answer_pipeline(self) -> None:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "Hikvision POC", "examiner_name": "Examiner"},
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]

        acquire = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "source": "synthetic_specimen", "vendor": "hikvision"},
        )
        self.assertEqual(acquire.status_code, 200)
        body = acquire.json()
        self.assertEqual(body.get("vendor"), "hikvision")
        device_id = body["evidence"]["id"]

        identification = self.client.get(f"/api/v1/devices/{device_id}/identification").json()
        hits = identification.get("hits") or []
        self.assertTrue(any(h.get("vendor") == "Hikvision" for h in hits))

        recover = self.client.post(
            f"/api/v1/devices/{device_id}/recover",
            json={"actor": "Examiner"},
        )
        job_id = recover.json()["job"]["id"]
        job = self._wait_job(job_id)
        self.assertEqual(job.get("status"), "completed")

        job_detail = self.client.get(f"/api/v1/jobs/{job_id}").json()
        segments = job_detail.get("segments") or []
        self.assertGreater(len(segments), 0)
        validations = {s.get("validation") for s in segments}
        self.assertTrue(any(v in {"hikbtree_indexed", "hikbtree_deleted_entry"} for v in validations), validations)
        # A cleared index entry whose data pointer still addresses the video area must reach
        # the Recovery page as deleted — docs/reference/hikvision_fs.md §7.
        self.assertIn("hikbtree_deleted_entry", validations)
        stored = list_sequences(device_id)
        device = get_device(device_id)
        assert device is not None
        self.assertGreater(len(stored), 0)
        source_bytes = Path(device["image_path"]).read_bytes()
        for sequence in stored:
            artifact = Path(sequence["output_path"])
            self.assertNotEqual(artifact.resolve(), Path(device["image_path"]).resolve())
            self.assertEqual(artifact.stat().st_size, sequence["byte_length"])
            self.assertEqual(
                artifact.read_bytes(),
                source_bytes[sequence["byte_start"] : sequence["byte_end"]],
            )
            self.assertIsNotNone(sequence["recorder_start_ts"])
            # §7.1 timestamp provenance ladder — indexed, residual, or IDR-table recovered.
            self.assertIn(
                sequence["timestamp_source"],
                {"hikbtree_entry", "hikbtree_residual", "idr_table_scan"},
            )
            self.assertEqual(sequence["parser_name"], "hikvision")
            self.assertTrue(sequence["signature_evidence"].get("hikbtree_index"))
            evidence = sequence["validation_evidence"]
            self.assertIn("allocation_state", evidence)
            self.assertEqual(evidence["resolution"], "320x240")

        # A deleted recording carries lower timestamp confidence than an allocated one.
        by_state = {seq["validation_evidence"]["allocation_state"]: seq for seq in stored}
        self.assertIn("deleted (index entry cleared)", by_state)
        self.assertLess(
            by_state["deleted (index entry cleared)"]["timestamp_confidence"],
            by_state["allocated"]["timestamp_confidence"],
        )


if __name__ == "__main__":
    unittest.main()
