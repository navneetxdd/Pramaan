"""Memory-safety contract for the Hikvision adapter on a desktop client.

The Tauri shell runs on ordinary laptops against images that can be multi-terabyte. Two things
must therefore never happen, and both regressed before:

1. materializing the mapping as a ``bytes`` object, and
2. retaining each segment's payload in ``raw_bytes``, which on a real drive with thousands of
   data blocks is gigabytes resident before a single artifact is written.

See docs/reference/hikvision_fs.md §10.
"""

from __future__ import annotations

import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path

from engine.app.parsers.hikvision import HikvisionAdapter
from engine.tests.support import hikvision_builder as builder

SPARSE_SIZE = 512 * 1024 * 1024
PEAK_ALLOCATION_BUDGET = 64 * 1024 * 1024


class HikvisionMmapMemoryTests(unittest.TestCase):
    """The emulated filesystem at the head of a large sparse file.

    Built once for the class: creating the file is the expensive part, not scanning it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="pramaan-hikmem-")
        cls.image = Path(cls._tmp.name) / "hikvision_sparse.img"
        with cls.image.open("wb") as handle:
            handle.write(builder.build_emulated_bytes())
            handle.truncate(SPARSE_SIZE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_scan_does_not_allocate_in_proportion_to_the_image(self) -> None:
        self.assertEqual(self.image.stat().st_size, SPARSE_SIZE)

        tracemalloc.start()
        try:
            segments = HikvisionAdapter().scan(self.image)
        finally:
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

        self.assertEqual(len(segments), builder.EXPECTED_RECORDING_COUNT)
        self.assertLess(
            peak,
            PEAK_ALLOCATION_BUDGET,
            f"peak allocation {peak} bytes scanning a {SPARSE_SIZE} byte image",
        )

    def test_segments_carry_byte_ranges_not_payloads(self) -> None:
        segments = HikvisionAdapter().scan(self.image)
        self.assertTrue(segments)
        self.assertEqual(sum(len(segment.raw_bytes) for segment in segments), 0)
        for segment in segments:
            self.assertGreater(segment.offset_end, segment.offset_start)

    def test_scan_of_a_sparse_image_completes_promptly(self) -> None:
        """Guards the C-level ``find`` scanning contract.

        The previous implementation byte-scanned in a Python ``range()`` loop, ~500k iterations
        per entry. That is a hang on real evidence, not a slow path.
        """
        started = time.monotonic()
        HikvisionAdapter().scan(self.image)
        self.assertLess(time.monotonic() - started, 20.0)

    def test_max_bytes_bounds_the_mapping(self) -> None:
        self.assertEqual(HikvisionAdapter().scan(self.image, max_bytes=0), [])
        # A window that stops before the HIKBTREE cannot enumerate recordings.
        self.assertEqual(HikvisionAdapter().scan(self.image, max_bytes=builder.VIDEO_AREA_OFFSET), [])


if __name__ == "__main__":
    unittest.main()
