from __future__ import annotations

from dataclasses import dataclass, field
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
    codec: str | None = None
    recorder_start_ts: str | None = None
    recorder_end_ts: str | None = None
    timestamp_source: str = "unavailable"
    timestamp_confidence: float | None = None
    parser_name: str = "unknown"
    parser_version: str = "1"
    signature_evidence: dict[str, object] = field(default_factory=dict)
    validation_evidence: dict[str, object] = field(default_factory=dict)


class RecoveryAdapter(Protocol):
    name: str
    vendor: str

    def scan(self, image_path: Path, *, max_bytes: int | None = None) -> list[RecoveredSegment]:
        ...
