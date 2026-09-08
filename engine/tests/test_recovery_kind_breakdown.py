from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault(
    "FORENSIC_WORKSTATION_DATA", tempfile.mkdtemp(prefix="forensic-kindbreak-")
)

from engine.app.core import db  # noqa: E402
from engine.app.parsers.filesystem_recovery import (  # noqa: E402
    build_fat16_deleted_fixture,
    filesystem_status,
)
from engine.app.services.recovery import run_recovery_job  # noqa: E402


class RecoveryResultMetadataTests(unittest.TestCase):
    """A2 + C14: the recovery job result must carry a per-kind breakdown that
    sums to the segment total, and every carve segment must carry an explicit
    allocation state so the UI never shows a blank cell."""

    def setUp(self) -> None:
        self._original_db_path = db.DATABASE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = Path(self._tmp.name)
        db.DATABASE_PATH = self._dir / "forensic.db"
        db.init_db()

    def tearDown(self) -> None:
        db.DATABASE_PATH = self._original_db_path
        self._tmp.cleanup()

    def _new_device(self, image_path: Path) -> None:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO cases (id, name, examiner_name, created_at) "
                "VALUES ('c','C','Examiner','2026-01-01T00:00:00Z')"
            )
            conn.execute(
                "INSERT INTO devices (id, case_id, image_path) VALUES ('d','c',?)",
                (str(image_path),),
            )

    def test_job_result_kind_breakdown_sums_to_segment_total(self) -> None:
        if not filesystem_status().available:
            self.skipTest("pytsk3 unavailable on this platform")

        img = self._dir / "fat16.img"
        img.write_bytes(build_fat16_deleted_fixture())
        self._new_device(img)

        asyncio.run(
            run_recovery_job("job", "c", "d", "Examiner", adapter="generic_tier2")
        )

        from engine.app.core.repository import get_persisted_job

        persisted = get_persisted_job("job")
        self.assertEqual(persisted["status"], "completed", persisted)
        result = json.loads(persisted["result_json"])

        self.assertIn("segments_by_kind", result)
        kinds = result["segments_by_kind"]
        self.assertGreater(result["segments_found"], 0)
        self.assertEqual(sum(kinds.values()), result["segments_found"])
        # A FAT undelete run is entirely filesystem_undelete; none of it is a
        # recorder recording.
        self.assertEqual(kinds["filesystem_undelete"], result["segments_found"])
        self.assertEqual(kinds["recording"], 0)

    def test_carve_segments_carry_an_explicit_allocation_state(self) -> None:
        from engine.app.core.repository import list_sequences
        from engine.app.services.recovery import classify_artifact_kind
        from engine.app.verification.lab_specimen import write_lab_specimen

        blob = self._dir / "dahua_carve.bin"
        write_lab_specimen(blob)
        self._new_device(blob)

        asyncio.run(
            run_recovery_job("job", "c", "d", "Examiner", adapter="dahua_dhav")
        )

        carve = [
            s
            for s in list_sequences("d")
            if classify_artifact_kind(s["validation_level"]) == "carve"
        ]
        self.assertTrue(carve, "DHAV carver should produce at least one carve segment")
        for seq in carve:
            evidence = seq.get("validation_evidence") or {}
            self.assertTrue(
                evidence.get("allocation_state"),
                f"carve segment {seq['id']} has a blank allocation_state",
            )


if __name__ == "__main__":
    unittest.main()
