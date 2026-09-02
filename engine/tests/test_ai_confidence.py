from __future__ import annotations

import unittest

from engine.app.services.ai_analytics import _analyze_sequence
from engine.app.verification.media_fixture import caviar_h264_annexb, ensure_playable_h264
from pathlib import Path
import tempfile


class AiConfidenceTests(unittest.TestCase):
    def test_findings_confidence_bounded_zero_to_one(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".h264", delete=False) as tmp:
            tmp.write(ensure_playable_h264(caviar_h264_annexb(max_frames=24)))
            video_path = Path(tmp.name)
        try:
            findings, _warnings, _frames = _analyze_sequence(video_path)
            for finding in findings:
                confidence = finding.get("confidence")
                self.assertIsNotNone(confidence)
                self.assertGreaterEqual(float(confidence), 0.0)
                self.assertLessEqual(float(confidence), 1.0)
        finally:
            video_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
