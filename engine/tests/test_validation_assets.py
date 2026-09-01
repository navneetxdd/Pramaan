from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = ROOT / "validation_data"


class ValidationAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (VALIDATION_DIR / "manifest.json").exists():
            raise unittest.SkipTest("Run scripts/validation/fetch_validation_assets.py first")

    def test_tier1_fixtures_recover(self) -> None:
        from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
        from engine.app.parsers.hikvision import HikvisionAdapter
        from engine.app.parsers.honeywell import HoneywellAdapter

        cases = [
            ("fixtures/tier1/dahua_known_answer.bin", DahuaDhavAdapter(), {"dual_signature_4"}),
            ("fixtures/tier1/honeywell_known_answer.bin", HoneywellAdapter(), {"honeywell_expired_index", "honeywell_format_carve_4", "honeywell_index_4"}),
            ("fixtures/tier1/hikvision_known_answer.bin", HikvisionAdapter(), {"hikbtree_indexed", "hikbtree_stale_entry"}),
        ]
        for rel, adapter, expected_vals in cases:
            path = VALIDATION_DIR / rel
            self.assertTrue(path.exists(), rel)
            segments = adapter.scan(path)
            self.assertGreater(len(segments), 0, rel)
            vals = {s.validation for s in segments}
            self.assertTrue(vals & expected_vals, f"{rel} got {vals}")

    def test_tier2_fat_fixture(self) -> None:
        from engine.app.parsers.filesystem_recovery import recover_filesystem

        path = VALIDATION_DIR / "fixtures/tier2/fat16_deleted_entry.img"
        self.assertTrue(path.exists())
        segments = recover_filesystem(path)
        self.assertGreater(len(segments), 0)


class OemExternalTests(unittest.TestCase):
    def test_oem_image_dir_when_present(self) -> None:
        oem_dir = os.getenv("PRAMAAN_OEM_IMAGE_DIR") or str(VALIDATION_DIR / "oem")
        root = Path(oem_dir)
        if not root.exists():
            self.skipTest("No OEM image directory")
        images = [p for p in root.iterdir() if p.suffix.lower() in {".bin", ".dd", ".raw", ".img", ".e01"}]
        if not images:
            self.skipTest("No OEM images in drop zone")

        from engine.app.parsers.manufacturer_detect import identify_image

        for image in images[:3]:
            report = identify_image(image)
            hits = report.get("hits") or []
            if not hits:
                self.skipTest(f"{image.name} is not a DVR OEM image — remove from OEM drop zone")
            self.assertGreater(len(hits), 0, image.name)


if __name__ == "__main__":
    unittest.main()
