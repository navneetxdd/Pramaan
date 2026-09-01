from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.unwrap import NAL_START_4, unwrap_to_h264
from engine.app.verification.lab_specimen import build_dahua_lab_specimen


class ExportPlayableTests(unittest.TestCase):
    def test_unwrap_produces_annexb_with_idr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dahua.bin"
            path.write_bytes(build_dahua_lab_specimen())
            segments = DahuaDhavAdapter().scan(path)
            self.assertGreater(len(segments), 0)
            chunk = path.read_bytes()[segments[0].offset_start : segments[0].offset_end]
            h264 = unwrap_to_h264(chunk)
            self.assertIn(NAL_START_4, h264)
            nal_types = set()
            idx = 0
            while idx < len(h264) - 4:
                if h264[idx : idx + 4] == NAL_START_4 and idx + 4 < len(h264):
                    nal_types.add(h264[idx + 4] & 0x1F)
                idx += 1
            self.assertTrue(nal_types & {1, 5}, f"expected slice/IDR NAL, got types {nal_types}")


if __name__ == "__main__":
    unittest.main()
