from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RecoveredSegment:
    channel: int | None
    vendor: str
    offset_start: int
    offset_end: int
    frame_count: int
    confidence: float
    validation: str
    raw_bytes: bytes


class RecoveryAdapter(Protocol):
    name: str
    vendor: str

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        ...
