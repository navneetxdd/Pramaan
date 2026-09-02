from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest

os.environ.setdefault("FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-e1-"))

from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@unittest.skipUnless(shutil.which("ffprobe"), "ffprobe not installed")
class E1ExportFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _export_frame_count(self, vendor: str) -> int:
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "E1 export", "examiner_name": "Examiner"},
        )
        case_id = created.json()["id"]
        acquire = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "source": "synthetic_specimen", "vendor": vendor},
        )
        device_id = acquire.json()["evidence"]["id"]
        recover = self.client.post(f"/api/v1/devices/{device_id}/recover", json={"actor": "Examiner"})
        job_id = recover.json()["job"]["id"]
        while self.client.get(f"/api/v1/jobs/{job_id}/status").json()["status"] not in {
            "completed",
            "failed",
        }:
            time.sleep(0.3)
        segment_id = self.client.get(f"/api/v1/devices/{device_id}/sequences").json()["segments"][0]["id"]
        exported = self.client.post(
            f"/api/v1/devices/{device_id}/sequences/{segment_id}/export",
            json={},
        )
        filename = exported.json()["filename"]
        with tempfile.NamedTemporaryFile(suffix=f"_{vendor}.mp4", delete=False) as tmp:
            tmp.write(self.client.get(f"/api/v1/files/{filename}").content)
            out_path = tmp.name
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                "stream=nb_read_frames",
                "-of",
                "csv=p=0",
                out_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return int((proc.stdout.strip() or "0").splitlines()[0])

    def test_dahua_exports_at_least_eight_frames(self) -> None:
        self.assertGreaterEqual(self._export_frame_count("dahua"), 8)

    def test_honeywell_exports_at_least_eight_frames(self) -> None:
        self.assertGreaterEqual(self._export_frame_count("honeywell"), 8)

    def test_hikvision_exports_at_least_eight_frames(self) -> None:
        self.assertGreaterEqual(self._export_frame_count("hikvision"), 8)


if __name__ == "__main__":
    unittest.main()
