from __future__ import annotations

import struct
import tempfile
import tracemalloc
import unittest
from pathlib import Path

from engine.app.parsers.hikvision import HikvisionAdapter
from engine.app.parsers.schemas.hikvision_fs import (
    HikbtreeEntry,
    MASTER_BLOCK_OFFSET,
    MPEG_PS_PACK,
    build_hikbtree_header,
    build_hikbtree_page,
    build_master_block,
)

HIKBTREE_OFFSET = 0x100000
PAGE_OFFSET = HIKBTREE_OFFSET + 0x100


class HikvisionMmapMemoryTests(unittest.TestCase):
    def test_scanning_large_image_does_not_allocate_whole_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "hikvision_sparse.bin"
            sparse_size = 512 * 1024 * 1024
            data_offset = sparse_size - (256 * 1024)
            entry = HikbtreeEntry(
                channel=1,
                start_unix=1_600_000_000,
                end_unix=1_600_000_100,
                data_offset=data_offset,
                has_footage=True,
                stale=False,
            )
            with image.open("wb") as handle:
                handle.truncate(sparse_size)
                handle.seek(MASTER_BLOCK_OFFSET)
                handle.write(
                    build_master_block(
                        hikbtree_offset=HIKBTREE_OFFSET,
                        hikbtree_size=0x1000,
                        init_time=1_600_000_000,
                        video_area_offset=data_offset,
                    )
                )
                handle.seek(HIKBTREE_OFFSET)
                handle.write(build_hikbtree_header(PAGE_OFFSET))
                handle.seek(PAGE_OFFSET)
                handle.write(build_hikbtree_page([entry]))
                handle.seek(data_offset)
                handle.write(MPEG_PS_PACK + struct.pack(">H", 0) + b"\x00" * 128)

            tracemalloc.start()
            try:
                segments = HikvisionAdapter().scan(image)
            finally:
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

            self.assertGreaterEqual(len(segments), 1)
            self.assertLess(peak, 200 * 1024 * 1024, f"peak allocation {peak} bytes too high")


if __name__ == "__main__":
    unittest.main()
