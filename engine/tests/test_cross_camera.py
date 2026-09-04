from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-ccam-")

from engine.app.core.config import OEM_IMAGE_DIR, REID_MODEL_PATH  # noqa: E402
from engine.app.core.db import init_db  # noqa: E402
from engine.app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DEMO_CAM_A = OEM_IMAGE_DIR / "demo_camA.mp4"


def _poll_job(client: TestClient, job_id: str, *, timeout_s: float = 60.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/v1/jobs/{job_id}").json()
        if status["status"] in ("completed", "failed"):
            return status
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} did not finish in {timeout_s}s")


class CrossCameraSourcesTests(unittest.TestCase):
    """list_sources() is pure DB/filesystem logic — no ONNX models required, always runs."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _new_case(self, name: str) -> str:
        r = self.client.post("/api/v1/cases", json={"name": name, "examiner_name": "Examiner"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["id"]

    def test_recovered_channel_appears_as_a_source(self) -> None:
        case_id = self._new_case("Cross-camera: recovered channel")
        acquired = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            json={"actor": "Examiner", "vendor": "dahua"},
        )
        self.assertEqual(acquired.status_code, 200, acquired.text)
        device_id = acquired.json()["evidence"]["id"]

        recover = self.client.post(f"/api/v1/devices/{device_id}/recover", json={"actor": "Examiner"})
        self.assertEqual(recover.status_code, 200, recover.text)
        status = _poll_job(self.client, recover.json()["job"]["id"])
        self.assertEqual(status["status"], "completed", status)

        sources = self.client.get(f"/api/v1/cases/{case_id}/cross-camera/sources")
        self.assertEqual(sources.status_code, 200, sources.text)
        body = sources.json()
        kinds = {s["kind"] for s in body["sources"]}
        self.assertIn("recovered_channel", kinds)
        self.assertIn("detector", body["models"])
        self.assertIn("reid", body["models"])
        self.assertIn("face", body["models"])

    @unittest.skipUnless(
        DEMO_CAM_A.exists(),
        "validation_data/oem/demo_camA.mp4 not present — operator sample, gitignored, not fetched in CI",
    )
    def test_registered_video_appears_as_a_source(self) -> None:
        case_id = self._new_case("Cross-camera: video evidence")
        acquired = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/oem",
            json={"actor": "Examiner", "filename": "demo_camA.mp4"},
        )
        self.assertEqual(acquired.status_code, 200, acquired.text)

        sources = self.client.get(f"/api/v1/cases/{case_id}/cross-camera/sources")
        self.assertEqual(sources.status_code, 200, sources.text)
        labels = {s["label"] for s in sources.json()["sources"]}
        self.assertIn("demo_camA.mp4", labels)

    def test_unknown_case_returns_404(self) -> None:
        r = self.client.get("/api/v1/cases/does-not-exist/cross-camera/sources")
        self.assertEqual(r.status_code, 404)


@unittest.skipUnless(
    REID_MODEL_PATH.exists() and DEMO_CAM_A.exists(),
    "Re-identification model and/or demo_camA.mp4/demo_camB.mp4 not present locally — "
    "run scripts/validation/fetch_validation_assets.py",
)
class CrossCameraCorrelationTests(unittest.TestCase):
    """Exercises the real ONNX pipeline end-to-end. Skipped where the model isn't present
    (CI doesn't fetch it), runs for real on a workstation that has."""

    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

        r = cls.client.post("/api/v1/cases", json={"name": "Cross-camera correlation", "examiner_name": "Examiner"})
        cls.case_id = r.json()["id"]
        for filename in ("demo_camA.mp4", "demo_camB.mp4"):
            acquired = cls.client.post(
                f"/api/v1/cases/{cls.case_id}/devices/acquire/oem",
                json={"actor": "Examiner", "filename": filename},
            )
            assert acquired.status_code == 200, acquired.text

        sources = cls.client.get(f"/api/v1/cases/{cls.case_id}/cross-camera/sources").json()
        source_keys = [s["key"] for s in sources["sources"]]

        run = cls.client.post(
            f"/api/v1/cases/{cls.case_id}/cross-camera/runs",
            json={
                "actor": "Examiner",
                "source_keys": source_keys,
                "fps": 1,
                "match_sensitivity": 0.55,
                "max_frames_per_source": 60,
            },
        )
        assert run.status_code == 200, run.text
        body = run.json()
        cls.run_id = body["run_id"]
        status = _poll_job(cls.client, body["job_id"], timeout_s=120)
        assert status["status"] == "completed", status

    def test_run_finds_at_least_one_identity(self) -> None:
        run = self.client.get(f"/api/v1/cross-camera/runs/{self.run_id}")
        self.assertEqual(run.status_code, 200, run.text)
        body = run.json()
        self.assertGreater(body["summary"]["identities"], 0)
        self.assertGreater(body["summary"]["detections"], 0)

    def test_search_ranks_a_crop_of_itself_highest(self) -> None:
        run = self.client.get(f"/api/v1/cross-camera/runs/{self.run_id}").json()
        self.assertTrue(run["identities"], "expected at least one identity to search against")
        identity = self.client.get(
            f"/api/v1/cross-camera/identities/{run['identities'][0]['id']}"
        ).json()
        appearance_id = identity["appearances"][0]["id"]

        crop = self.client.get(f"/api/v1/cross-camera/appearances/{appearance_id}/crop")
        self.assertEqual(crop.status_code, 200, crop.text)

        search = self.client.post(
            f"/api/v1/cross-camera/runs/{self.run_id}/search",
            files={"image": ("query.jpg", crop.content, "image/jpeg")},
            data={"mode": "appearance"},
        )
        self.assertEqual(search.status_code, 200, search.text)
        matches = search.json()["matches"]
        self.assertTrue(matches)
        # Searching with a crop of one of its own appearances should rank that same
        # identity's appearances at (or extremely near) the top.
        self.assertEqual(matches[0]["identity_id"], identity["id"])
        self.assertGreater(matches[0]["similarity"], 0.9)


if __name__ == "__main__":
    unittest.main()
