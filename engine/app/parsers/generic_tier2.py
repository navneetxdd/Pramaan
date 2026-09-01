from __future__ import annotations

import logging
from pathlib import Path

from engine.app.parsers.base import RecoveredSegment
from engine.app.parsers.filesystem_recovery import filesystem_status, recover_filesystem
from engine.app.parsers.generic_fallback import H264CarveAdapter

logger = logging.getLogger("forensic.engine")


class GenericTier2Adapter:
    """Tier 2 generic recovery: filesystem undelete when pytsk3 is present, else H.264 carve."""

    name = "generic_tier2"
    vendor = "Generic"

    def __init__(self) -> None:
        self._carve = H264CarveAdapter()

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        status = filesystem_status()
        segments: list[RecoveredSegment] = []

        if status.available:
            try:
                segments = recover_filesystem(image_path)
                if segments:
                    logger.info("Filesystem recovery found %s artifact(s) via %s", len(segments), status.backend)
                    return segments
            except Exception:
                logger.exception("Filesystem recovery failed — degrading to H.264 carve")

        carved = self._carve.scan(image_path, max_bytes=max_bytes)
        return [
            RecoveredSegment(
                channel=seg.channel,
                vendor=self.vendor,
                offset_start=seg.offset_start,
                offset_end=seg.offset_end,
                frame_count=seg.frame_count,
                confidence=min(seg.confidence, 0.55),
                validation="offset-ordered, timestamp unverified",
                raw_bytes=seg.raw_bytes,
                codec=seg.codec,
                parser_name=self.name,
                parser_version="2",
                signature_evidence=seg.signature_evidence,
                validation_evidence={
                    **seg.validation_evidence,
                    "timestamp_available": False,
                    "ordering_basis": "byte_offset",
                },
            )
            for seg in carved
        ]

    @staticmethod
    def degradation_message() -> str:
        return filesystem_status().detail
