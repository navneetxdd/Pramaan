from __future__ import annotations

import unittest

from engine.app.verification.media_fixture import NalPayloadSource, split_annexb_nals


def _nal_type(nal: bytes) -> int | None:
    if nal.startswith(b"\x00\x00\x00\x01") and len(nal) > 4:
        return nal[4] & 0x1F
    if nal.startswith(b"\x00\x00\x01") and len(nal) > 3:
        return nal[3] & 0x1F
    return None


class MediaFixtureTests(unittest.TestCase):
    def test_access_unit_has_param_sets_and_idr(self) -> None:
        source = NalPayloadSource()
        unit = source.next_decodable_access_unit(min_len=64)
        types = {_nal_type(n) for n in split_annexb_nals(unit) if _nal_type(n) is not None}
        self.assertIn(7, types)
        self.assertIn(8, types)
        self.assertIn(5, types)
        self.assertGreaterEqual(len(unit), 64)


if __name__ == "__main__":
    unittest.main()
