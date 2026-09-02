from __future__ import annotations

import os
import tempfile
import unittest

from pathlib import Path

from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.hikvision import HikvisionAdapter
from engine.app.parsers.schemas.dhav import validate_dhav_frame
from engine.app.verification.hikvision_specimen import build_hikvision_lab_specimen
from engine.app.verification.lab_specimen import build_dahua_lab_specimen


class DhavParserGoldenTests(unittest.TestCase):
    def test_lab_specimen_frames_pass_four_check_validation(self) -> None:
        blob = build_dahua_lab_specimen()
        validated = 0
        offset = 0
        while True:
            hit = blob.find(b"DHAV", offset)
            if hit < 0:
                break
            result = validate_dhav_frame(blob, hit)
            if result and result.ok:
                validated += 1
                self.assertTrue(all(result.checks.values()))
                self.assertEqual(result.validation_level, "dual_signature_4")
            offset = hit + 4
        self.assertGreater(validated, 0)

    def test_adapter_recovers_specimen_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specimen.bin"
            path.write_bytes(build_dahua_lab_specimen())
            segments = DahuaDhavAdapter().scan(path)
        self.assertGreater(len(segments), 0)
        self.assertTrue(any(s.validation == "dual_signature_4" for s in segments))
        self.assertTrue(any(s.validation == "unreferenced_carve" for s in segments))
        self.assertTrue(any(s.recorder_start_ts for s in segments))
        self.assertTrue(any(s.timestamp_source == "dhav_header_date" for s in segments))
        unreferenced = [s for s in segments if s.validation == "unreferenced_carve"]
        self.assertEqual(unreferenced[0].validation_evidence.get("recovery_context"), "unreferenced_carve")


class HikvisionParserGoldenTests(unittest.TestCase):
    def test_lab_specimen_uses_hikbtree_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specimen.bin"
            path.write_bytes(build_hikvision_lab_specimen())
            segments = HikvisionAdapter().scan(path)
        self.assertGreater(len(segments), 0)
        self.assertTrue(all(s.validation in {"hikbtree_indexed", "hikbtree_stale_entry"} for s in segments))
        self.assertTrue(any(s.timestamp_source == "hikbtree_entry" for s in segments))


if __name__ == "__main__":
    unittest.main()
