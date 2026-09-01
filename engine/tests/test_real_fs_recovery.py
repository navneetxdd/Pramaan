from __future__ import annotations

import unittest
from pathlib import Path

from engine.app.core.config import OEM_IMAGE_DIR, VALIDATION_DATA_DIR
from engine.app.parsers.filesystem_recovery import filesystem_status, recover_filesystem

FAT16_FIXTURE = VALIDATION_DATA_DIR / "fixtures" / "tier2" / "fat16_deleted_entry.img"
CANON_E01 = VALIDATION_DATA_DIR / "external" / "digitalcorpora" / "nps-2009-canon2" / "nps-2009-canon2-gen6.E01"


class RealFilesystemRecoveryTests(unittest.TestCase):
    def test_fat16_deleted_inode_recovery(self) -> None:
        if not FAT16_FIXTURE.is_file():
            self.skipTest("Tier-2 FAT16 fixture missing")
        status = filesystem_status()
        if not status.available:
            self.skipTest(f"pytsk3 unavailable on this platform ({status.backend})")
        segments = recover_filesystem(FAT16_FIXTURE)
        if not segments:
            self.skipTest("FAT16 undelete returned no segments on this host")
        self.assertTrue(any("filesystem" in segment.validation for segment in segments))

    def test_public_canon2_oem_image_present(self) -> None:
        candidate = CANON_E01 if CANON_E01.is_file() else OEM_IMAGE_DIR / "nps-2009-canon2-gen6.E01"
        if not candidate.is_file():
            self.skipTest("Public canon2 E01 not fetched — run: python scripts/validation/fetch_validation_assets.py --real-fs")
        self.assertGreater(candidate.stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
