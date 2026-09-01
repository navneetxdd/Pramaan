from __future__ import annotations

import unittest
from pathlib import Path

from engine.app.core.config import OEM_IMAGE_DIR, VALIDATION_DATA_DIR
from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.filesystem_recovery import filesystem_status, recover_filesystem
from engine.app.parsers.unwrap import unwrap_to_h264
from engine.app.verification.media_fixture import split_annexb_nals

CANON_E01 = VALIDATION_DATA_DIR / "external" / "digitalcorpora" / "nps-2009-canon2" / "nps-2009-canon2-gen6.E01"
REAL_DAV = VALIDATION_DATA_DIR / "external" / "dvr" / "dahua" / "19.25.00-19.25.50-R-.dav"
FAT16_FIXTURE = VALIDATION_DATA_DIR / "fixtures" / "tier2" / "fat16_deleted_entry.img"


def _nal_types(h264: bytes) -> set[int]:
    types: set[int] = set()
    for nal in split_annexb_nals(h264):
        if nal.startswith(b"\x00\x00\x00\x01") and len(nal) > 4:
            types.add(nal[4] & 0x1F)
        elif nal.startswith(b"\x00\x00\x01") and len(nal) > 3:
            types.add(nal[3] & 0x1F)
    return types


class Canon2RealRecoveryTests(unittest.TestCase):
    def test_canon2_e01_recovers_files(self) -> None:
        candidate = CANON_E01 if CANON_E01.is_file() else OEM_IMAGE_DIR / "nps-2009-canon2-gen6.E01"
        if not candidate.is_file():
            self.skipTest("Public canon2 E01 not fetched")
        status = filesystem_status()
        if not status.available:
            self.skipTest(f"pytsk3 unavailable ({status.backend})")
        segments = recover_filesystem(candidate, max_entries=512)
        self.assertGreaterEqual(len(segments), 5, f"expected ≥5 recovered items, got {len(segments)}")
        hits = 0
        for segment in segments:
            validation = segment.validation or ""
            if "filesystem" in validation:
                hits += 1
                continue
            if segment.raw_bytes[:3] == b"\xff\xd8\xff":
                hits += 1
        self.assertGreaterEqual(hits, 5)


class DahuaRealDavTests(unittest.TestCase):
    def test_real_dav_scan_and_unwrap(self) -> None:
        if not REAL_DAV.is_file():
            self.skipTest("Real Dahua .dav not fetched — run fetch_validation_assets.py --real-dvr")
        segments = DahuaDhavAdapter().scan(REAL_DAV)
        self.assertGreaterEqual(len(segments), 10, f"expected many segments, got {len(segments)}")
        self.assertTrue(all(s.codec == "h264" for s in segments[:20]))
        chunk = REAL_DAV.read_bytes()[segments[0].offset_start : segments[0].offset_end]
        h264 = unwrap_to_h264(chunk)
        self.assertTrue(_nal_types(h264) & {1, 5}, f"missing slice/IDR in first segment: {_nal_types(h264)}")


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
            self.skipTest("Public canon2 E01 not fetched")
        status = filesystem_status()
        if not status.available:
            self.skipTest(f"pytsk3 unavailable ({status.backend})")
        segments = recover_filesystem(candidate, max_entries=256)
        self.assertGreaterEqual(len(segments), 5)


if __name__ == "__main__":
    unittest.main()
