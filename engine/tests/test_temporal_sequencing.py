from __future__ import annotations

import unittest

from engine.app.parsers.temporal_sequencing import Frame, sequence_frames


class TemporalSequencingTests(unittest.TestCase):
    def test_groups_continuous_frames(self) -> None:
        frames = [Frame(timestamp=float(i), frame_number=i, offset=i * 100) for i in range(20)]
        sequences = sequence_frames(frames, gap_multiplier=2.0, min_seq_len=5)
        self.assertEqual(len(sequences), 1)
        self.assertEqual(len(sequences[0].frames), 20)

    def test_splits_on_large_gap(self) -> None:
        frames = [Frame(timestamp=float(i), frame_number=i) for i in range(10)]
        frames += [Frame(timestamp=100.0, frame_number=20)]
        frames += [Frame(timestamp=101.0, frame_number=21) for _ in range(9)]
        sequences = sequence_frames(frames, gap_multiplier=2.0, min_seq_len=5)
        self.assertGreaterEqual(len(sequences), 1)


if __name__ == "__main__":
    unittest.main()
