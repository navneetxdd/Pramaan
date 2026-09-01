from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path

os.environ["FORENSIC_WORKSTATION_DATA"] = tempfile.mkdtemp(prefix="forensic-m4-test-")
os.environ["FORENSIC_CHECKPOINT_MB"] = "1"

from engine.app.core.config import CHECKPOINT_INTERVAL, CHUNK_SIZE  # noqa: E402
from engine.app.core.db import get_db, init_db  # noqa: E402
from engine.app.core.hashing import hash_file  # noqa: E402
from engine.app.core.repository import (  # noqa: E402
    create_case,
    get_device,
    register_pending_device,
    save_acquisition_checkpoint,
    update_device_acquisition,
    verify_device_integrity,
    case_storage_dir,
)
from engine.app.services.disk_enumeration import list_imaging_sources  # noqa: E402
from engine.app.services.physical_imaging import (  # noqa: E402
    _hash_objects_from_file,
    _read_with_sector_recovery,
    prepare_imaging_device,
    run_imaging_job,
)
from fastapi.testclient import TestClient  # noqa: E402
from engine.app.main import app  # noqa: E402


class M4AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        cls.client = TestClient(app)

    def _make_source(self, size: int) -> Path:
        path = Path(tempfile.mkdtemp()) / "source.bin"
        block = b"P" * min(size, CHUNK_SIZE)
        written = 0
        with path.open("wb") as handle:
            while written < size:
                chunk = block[: min(len(block), size - written)]
                handle.write(chunk)
                written += len(chunk)
        return path

    def test_checkpoint_persisted(self) -> None:
        case = create_case("Checkpoint", "Examiner")
        dest = case_storage_dir(case["id"]) / "chk.dd"
        device = register_pending_device(case["id"], dest)
        save_acquisition_checkpoint(device["id"], 4096)
        from engine.app.core.repository import get_latest_acquisition_checkpoint

        row = get_latest_acquisition_checkpoint(device["id"])
        assert row is not None
        self.assertEqual(row["bytes_written"], 4096)

    def test_bad_read_zero_fills_only_the_failed_sector(self) -> None:
        class SectorFaultSource:
            def __init__(self) -> None:
                self.position = 0
                self.data = b"A" * 1536

            def seek(self, offset: int) -> None:
                self.position = offset

            def read(self, size: int) -> bytes:
                if size > 512 or self.position == 512:
                    raise OSError("simulated read fault")
                start = self.position
                return self.data[start : start + size]

        recovered, bad_offsets = _read_with_sector_recovery(SectorFaultSource(), None, 0, 1536)
        self.assertEqual(bad_offsets, [512])
        self.assertEqual(recovered[:512], b"A" * 512)
        self.assertEqual(recovered[512:1024], b"\x00" * 512)
        self.assertEqual(recovered[1024:], b"A" * 512)

    def test_file_imaging_end_to_end(self) -> None:
        source = self._make_source(256 * 1024)
        expected_md5, expected_sha = hash_file(source)
        case = create_case("M4 imaging", "Examiner")
        case_id = case["id"]

        device = prepare_imaging_device(case_id, "Examiner", str(source))
        job_id = uuid.uuid4().hex

        asyncio.run(
            run_imaging_job(
                job_id,
                case_id,
                device["id"],
                "Examiner",
                source_path=str(source),
            )
        )

        updated = get_device(device["id"])
        assert updated is not None
        self.assertEqual(updated["acquisition_status"], "complete")
        self.assertEqual(updated["image_md5"], expected_md5)
        self.assertEqual(updated["image_sha256"], expected_sha)
        integrity = verify_device_integrity(device["id"])
        self.assertTrue(integrity["ok"])

    def test_imaging_resume_from_checkpoint(self) -> None:
        source = self._make_source(512 * 1024)
        expected_md5, expected_sha = hash_file(source)
        case = create_case("M4 resume", "Examiner")
        case_id = case["id"]
        device = prepare_imaging_device(case_id, "Examiner", str(source))
        device_id = device["id"]
        dest = Path(device["image_path"])

        half = 256 * 1024
        with source.open("rb") as src, dest.open("wb") as out:
            chunk = src.read(half)
            out.write(chunk)
        md5_obj, sha_obj = _hash_objects_from_file(dest)
        save_acquisition_checkpoint(device_id, half)
        update_device_acquisition(device_id, status="interrupted", bad_sector_map={"source_path": str(source)})

        job_id = uuid.uuid4().hex
        asyncio.run(
            run_imaging_job(
                job_id,
                case_id,
                device_id,
                "Examiner",
                source_path=str(source),
                resume=True,
            )
        )

        updated = get_device(device_id)
        assert updated is not None
        self.assertEqual(updated["acquisition_status"], "complete")
        self.assertEqual(updated["image_sha256"], expected_sha)
        self.assertEqual(updated["image_md5"], expected_md5)

    def test_acquisition_api_physical_start(self) -> None:
        source = self._make_source(128 * 1024)
        created = self.client.post(
            "/api/v1/cases",
            json={"name": "API M4", "examiner_name": "Tester"},
        )
        case_id = created.json()["id"]
        response = self.client.post(
            f"/api/v1/cases/{case_id}/devices/acquire/physical",
            json={"actor": "Tester", "source_path": str(source), "source_type": "file"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("job", body)
        self.assertIn("events_url", body)

    def test_list_disks_endpoint(self) -> None:
        response = self.client.get("/api/v1/acquisition/disks")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("disks", body)
        self.assertIsInstance(list_imaging_sources(), list)

    def test_drift_calibration(self) -> None:
        source = self._make_source(64 * 1024)
        case = create_case("Drift", "Examiner")
        dest = case_storage_dir(case["id"]) / "drift.dd"
        device = register_pending_device(case["id"], dest)
        update_device_acquisition(device["id"], status="complete", md5="x", sha256="y")

        response = self.client.post(
            f"/api/v1/devices/{device['id']}/drift-calibration",
            json={"reference_wall_unix": 1_700_000_000.0, "reference_device_unix": 1_699_999_900.0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json()["drift_offset_seconds"], 100.0)


if __name__ == "__main__":
    unittest.main()
