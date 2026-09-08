from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.services.evidence_provenance import (
    BUILDER_IMAGE_BANNER,
    detect_acquisition_class,
)
from engine.app.verification.builder_specimen import write_builder_specimen
from engine.app.verification.hikvision_specimen import write_hikvision_specimen
from engine.app.verification.honeywell_specimen import write_honeywell_specimen


class AcquisitionClassDetectionTests(unittest.TestCase):
    """B10: every builder image this tool writes must be flagged as a builder
    image by detect_acquisition_class, which only reads the first 512 bytes."""

    def _detect(self, writer) -> dict | None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image.bin"
            writer(path)
            return detect_acquisition_class(path)

    def test_dahua_builder_image_is_flagged(self) -> None:
        self.assertEqual(
            self._detect(write_builder_specimen),
            {
                "class": "builder_image",
                "authenticity": "tool_generated",
                "message": BUILDER_IMAGE_BANNER,
            },
        )

    def test_hikvision_builder_image_is_flagged(self) -> None:
        result = self._detect(write_hikvision_specimen)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["class"], "builder_image")

    def test_honeywell_builder_image_is_flagged(self) -> None:
        result = self._detect(write_honeywell_specimen)
        self.assertIsNotNone(
            result, "Honeywell builder marker not in the first 512 bytes"
        )
        assert result is not None
        self.assertEqual(result["class"], "builder_image")

    def test_plain_bytes_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "real.bin"
            path.write_bytes(b"\x00" * 4096)
            self.assertIsNone(detect_acquisition_class(path))


if __name__ == "__main__":
    unittest.main()
