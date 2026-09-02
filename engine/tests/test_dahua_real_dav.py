from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.app.core.config import VALIDATION_DATA_DIR
from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter

REAL_DAV_CANDIDATES = (
    VALIDATION_DATA_DIR / "oem" / "dahua_19.25.00-19.25.50-R.dav",
    Path(r"C:\Users\navne\Downloads\pramaan-real-data\dahua_19.25.00-19.25.50-R.dav"),
)


def _resolve_real_dav() -> Path | None:
    for candidate in REAL_DAV_CANDIDATES:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


class DahuaRealDavTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dav_path = _resolve_real_dav()
        if cls.dav_path is None:
            raise unittest.SkipTest("real Dahua .dav sample not staged")

    def test_scan_finds_video_segments_with_2017_timestamps(self) -> None:
        segments = DahuaDhavAdapter().scan(self.dav_path)
        video_segments = [s for s in segments if s.codec == "h264" and s.validation != "unreferenced_carve"]
        self.assertGreaterEqual(len(video_segments), 3)
        dated = [s for s in video_segments if s.recorder_start_ts and "2017" in s.recorder_start_ts]
        self.assertGreater(len(dated), 0)
        large = [s for s in video_segments if (s.offset_end - s.offset_start) >= 10_000]
        self.assertTrue(any(s.validation == "dual_signature_4" for s in large))

    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe not installed")
    def test_exported_largest_segment_decodes_many_frames(self) -> None:
        from engine.app.parsers.unwrap import unwrap_to_h264
        from engine.app.verification.media_fixture import ensure_playable_h264

        segments = DahuaDhavAdapter().scan(self.dav_path)
        largest = max(segments, key=lambda s: s.offset_end - s.offset_start)
        blob = self.dav_path.read_bytes()
        chunk = largest.raw_bytes or blob[largest.offset_start : largest.offset_end]
        payload = ensure_playable_h264(unwrap_to_h264(chunk))
        with tempfile.NamedTemporaryFile(suffix=".h264", delete=False) as tmp:
            tmp.write(payload)
            h264_path = tmp.name
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-show_entries",
                    "stream=nb_read_frames",
                    "-of",
                    "csv=p=0",
                    h264_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            frames = int((proc.stdout.strip() or "0").splitlines()[0])
            self.assertGreaterEqual(frames, 50)
            self.assertNotIn("Invalid data", proc.stderr)
        finally:
            os.unlink(h264_path)


if __name__ == "__main__":
    unittest.main()
