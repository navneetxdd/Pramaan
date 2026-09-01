from __future__ import annotations

import unittest

from engine.app.parsers.unwrap import NAL_START_4
from engine.app.verification.media_fixture import (
    caviar_h264_annexb,
    caviar_nal_units,
    split_annexb_nals,
)
from engine.app.verification.lab_specimen import build_dahua_lab_specimen


class MediaFixtureTests(unittest.TestCase):
    def test_annexb_starts_with_start_code(self) -> None:
        data = caviar_h264_annexb()
        self.assertTrue(data.startswith(NAL_START_4) or data.startswith(b"\x00\x00\x01"))

    def test_nal_split_count_positive(self) -> None:
        nals = caviar_nal_units()
        self.assertGreater(len(nals), 0)
        self.assertTrue(all(n.startswith(NAL_START_4) or n.startswith(b"\x00\x00\x01") for n in nals))

    def test_split_matches_cached_list(self) -> None:
        data = caviar_h264_annexb()
        self.assertEqual(len(split_annexb_nals(data)), len(caviar_nal_units()))

    def test_dahua_specimen_contains_annexb(self) -> None:
        blob = build_dahua_lab_specimen()
        self.assertIn(NAL_START_4, blob)


if __name__ == "__main__":
    unittest.main()
