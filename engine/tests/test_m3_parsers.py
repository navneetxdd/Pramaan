from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.app.parsers.filesystem_recovery import (
    build_fat16_deleted_fixture,
    filesystem_status,
    recover_filesystem,
)
from engine.app.parsers.generic_tier2 import GenericTier2Adapter
from engine.app.parsers.honeywell import HoneywellAdapter
from engine.app.parsers.schemas.honeywell import detect_honeywell_layout, validate_nal_header
from engine.app.verification.honeywell_specimen import build_honeywell_lab_specimen


class HoneywellParserTests(unittest.TestCase):
    def test_specimen_layout_detected(self) -> None:
        blob = build_honeywell_lab_specimen()
        layout = detect_honeywell_layout(blob)
        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertTrue(layout.machine_data_found)

    def test_nal_headers_in_specimen(self) -> None:
        blob = build_honeywell_lab_specimen()
        found = 0
        offset = 0
        while True:
            hit = blob.find(b"\x80\x01\x00", offset)
            if hit < 2 or hit >= len(blob):
                break
            parsed = validate_nal_header(blob, hit - 1)
            if parsed:
                found += 1
            offset = hit + 1
        self.assertGreaterEqual(found, 3)

    def test_both_deletion_mechanisms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "honeywell.bin"
            path.write_bytes(build_honeywell_lab_specimen())
            segments = HoneywellAdapter().scan(path)
        validations = {s.validation for s in segments}
        self.assertIn("honeywell_expired_index", validations)
        self.assertIn("honeywell_format_carve_4", validations)
        self.assertGreaterEqual(len(segments), 3)

    def test_scan_does_not_use_whole_image_read_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "honeywell.bin"
            path.write_bytes(build_honeywell_lab_specimen())
            with patch.object(Path, "read_bytes", side_effect=AssertionError("whole-image read attempted")):
                segments = HoneywellAdapter().scan(path)
        self.assertGreaterEqual(len(segments), 3)
        self.assertTrue(all(segment.parser_name == "honeywell" for segment in segments))
        self.assertTrue(any(segment.recorder_start_ts for segment in segments))


class FilesystemRecoveryTests(unittest.TestCase):
    def test_pytsk3_status(self) -> None:
        status = filesystem_status()
        self.assertTrue(status.available)
        self.assertEqual(status.backend, "pytsk3")

    def test_fat_deleted_file_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fat16.img"
            path.write_bytes(build_fat16_deleted_fixture())
            segments = recover_filesystem(path)
        self.assertGreater(len(segments), 0)
        self.assertTrue(any("filesystem" in s.validation for s in segments))

    def test_generic_tier2_prefers_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fat16.img"
            path.write_bytes(build_fat16_deleted_fixture())
            segments = GenericTier2Adapter().scan(path)
        self.assertGreater(len(segments), 0)


if __name__ == "__main__":
    unittest.main()
