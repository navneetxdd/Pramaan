from __future__ import annotations

import collections
import itertools
import statistics
from dataclasses import dataclass


@dataclass
class Frame:
    timestamp: float
    frame_number: int | None = None
    offset: int = 0
    channel: int | None = None
    raw: bytes = b""


@dataclass
class Sequence:
    frames: list[Frame]

    @property
    def channel(self) -> int | None:
        return self.frames[0].channel if self.frames else None


def sequence_frames(
    frames: list[Frame],
    gap_multiplier: float = 2.0,
    min_seq_len: int = 10,
) -> list[Sequence]:
    if not frames:
        return []
    frames = sorted(frames, key=lambda f: f.timestamp)
    sequences: list[Sequence] = []
    current: list[Frame] = [frames[0]]
    recent_intervals: collections.deque[float] = collections.deque(maxlen=50)

    for prev, frame in itertools.pairwise(frames):
        interval = frame.timestamp - prev.timestamp
        recent_intervals.append(interval)
        median_interval = statistics.median(recent_intervals) if recent_intervals else interval
        threshold = median_interval * gap_multiplier
        frame_number_gap = (
            abs(frame.frame_number - prev.frame_number)
            if frame.frame_number is not None and prev.frame_number is not None
            else 0
        )
        is_gap = interval > threshold or frame_number_gap > 2
        if is_gap:
            if len(current) >= min_seq_len:
                sequences.append(Sequence(current))
            current = [frame]
        else:
            current.append(frame)

    if len(current) >= min_seq_len:
        sequences.append(Sequence(current))
    return sequences
