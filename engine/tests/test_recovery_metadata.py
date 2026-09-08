from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.core import db
from engine.app.core.repository import insert_sequence


class RecoveryMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_database_path = db.DATABASE_PATH
        self._temporary_directory = tempfile.TemporaryDirectory()
        db.DATABASE_PATH = Path(self._temporary_directory.name) / "forensic.db"
        db.init_db()
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO cases (id, name, examiner_name, created_at) VALUES ('case', 'Case', 'Examiner', '2026-01-01T00:00:00Z')"
            )
            conn.execute(
                "INSERT INTO devices (id, case_id, image_path) VALUES ('device', 'case', 'evidence.bin')"
            )

    def tearDown(self) -> None:
        db.DATABASE_PATH = self._original_database_path
        self._temporary_directory.cleanup()

    def _insert(self, recorder_timestamp: str | None) -> dict:
        return insert_sequence(
            "device",
            channel=1,
            start_ts_raw=recorder_timestamp,
            end_ts_raw=recorder_timestamp,
            confidence="high",
            validation_level="four_checks",
            output_path="segment.bin",
            output_md5="md5",
            output_sha256="sha256",
            frame_count=1,
            drift_offset=60,
            byte_start=128,
            byte_end=256,
            codec="h264",
            offset_order=0,
            timestamp_source="recorder_header" if recorder_timestamp else "unavailable",
            timestamp_confidence=0.9 if recorder_timestamp else None,
            parser_name="test_parser",
            parser_version="2",
            signature_evidence={"header": True},
            validation_evidence={"length": True},
        )

    def test_schema_v5_persists_byte_and_parser_evidence(self) -> None:
        row = self._insert(None)
        self.assertEqual(db.SCHEMA_VERSION, 10)
        self.assertEqual(row["byte_start"], 128)
        self.assertEqual(row["byte_end"], 256)
        self.assertEqual(row["byte_length"], 128)
        self.assertIsNone(row["recorder_start_ts"])
        self.assertIsNone(row["corrected_start_ts"])
        self.assertEqual(row["parser_name"], "test_parser")

    def test_drift_applies_only_to_parseable_recorder_time(self) -> None:
        parsed = self._insert("2026-01-01T00:00:00Z")
        unparseable = self._insert("not-a-recorder-time")
        self.assertEqual(parsed["corrected_start_ts"], "2026-01-01T00:01:00Z")
        self.assertIsNone(unparseable["corrected_start_ts"])
        self.assertEqual(unparseable["byte_start"], 128)

    def test_sequences_list_exposes_openable_artifact_fields(self) -> None:
        # A filesystem-undelete fragment (here a 1-byte directory remnant) must
        # still arrive with a real output_path, a byte range, a human validation
        # label and an artifact kind, so the examiner can open it and is not
        # shown a blank row that reads as a recording.
        from engine.app.services.recovery import segments_as_legacy

        insert_sequence(
            "device",
            channel=0,
            start_ts_raw=None,
            end_ts_raw=None,
            confidence="high",
            validation_level="filesystem_deleted_inode",
            output_path="/case/sequences/job_000000.bin",
            output_md5="md5",
            output_sha256="sha256",
            frame_count=0,
            drift_offset=0,
            byte_start=0,
            byte_end=1,
            codec=None,
            offset_order=0,
            timestamp_source="unavailable",
            timestamp_confidence=None,
            parser_name="filesystem_recovery",
            parser_version="1",
            signature_evidence={},
            validation_evidence={"recovery_status": "intact"},
        )
        rows = segments_as_legacy("device")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["output_path"], "/case/sequences/job_000000.bin")
        self.assertEqual(row["byte_start"], 0)
        self.assertEqual(row["byte_end"], 1)
        self.assertEqual(row["byte_length"], 1)
        self.assertEqual(row["artifact_kind"], "filesystem_undelete")
        self.assertEqual(row["artifact_kind_label"], "Filesystem undelete")
        self.assertNotIn(row["validation_label"], ("", None))
        self.assertNotEqual(row["validation_label"], "filesystem_deleted_inode")

    def test_artifact_kind_never_labels_a_carve_as_a_recording(self) -> None:
        from engine.app.services.recovery import classify_artifact_kind

        self.assertEqual(
            classify_artifact_kind("filesystem_unallocated"), "filesystem_undelete"
        )
        self.assertEqual(classify_artifact_kind("unreferenced_carve"), "carve")
        self.assertEqual(
            classify_artifact_kind("offset-ordered, timestamp unverified"), "carve"
        )
        self.assertEqual(classify_artifact_kind("header_footer_only"), "carve")
        self.assertEqual(classify_artifact_kind("dual_signature_4"), "recording")
        self.assertEqual(classify_artifact_kind("hikbtree_indexed"), "recording")
        self.assertEqual(classify_artifact_kind(None), "carve")
        self.assertEqual(classify_artifact_kind("token_a_future_parser_adds"), "carve")


if __name__ == "__main__":
    unittest.main()
