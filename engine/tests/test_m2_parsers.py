from __future__ import annotations

import os
import tempfile
import unittest

from pathlib import Path

from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.hikvision import HikvisionAdapter
from engine.app.parsers.schemas.dhav import validate_dhav_frame
from engine.app.parsers.schemas.hkvi import seal_hkvi_block, validate_hkvi_block
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
        unreferenced = [s for s in segments if s.validation == "unreferenced_carve"]
        self.assertEqual(unreferenced[0].validation_evidence.get("recovery_context"), "unreferenced_carve")


class HkviParserGoldenTests(unittest.TestCase):
    def test_sealed_block_passes_four_check_validation(self) -> None:
        payload = b"\x00" * 128 + b"\x00\x00\x00\x01\x65" + b"\xab" * 64
        block = seal_hkvi_block(payload, channel=2)
        result = validate_hkvi_block(block, 0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(result.validation_level, "hkvi_block_4")

    def test_adapter_finds_sealed_blocks(self) -> None:
        blob = seal_hkvi_block(b"\x00" * 256, channel=1) + b"\xff" * 64 + seal_hkvi_block(b"\x00" * 192, channel=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hkvi.bin"
            path.write_bytes(blob)
            segments = HikvisionAdapter().scan(path)
        self.assertEqual(len(segments), 2)
        self.assertTrue(all(s.validation == "hkvi_block_4" for s in segments))


if __name__ == "__main__":
    unittest.main()
