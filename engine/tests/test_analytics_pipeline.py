from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine.app.services import ai_analytics


class AnalyticsPipelineTests(unittest.TestCase):
    def test_motion_and_scene_change_are_distinct_findings(self) -> None:
        if not ai_analytics._load_cv():
            self.skipTest("OpenCV is unavailable")
        cv2, np = ai_analytics._cv2, ai_analytics._np
        assert cv2 is not None and np is not None

        video_path = Path(tempfile.mkdtemp(prefix="pramaan-analytics-")) / "changes.avi"
        writer = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"MJPG"),
            10,
            (320, 240),
        )
        self.assertTrue(writer.isOpened())
        try:
            for index in range(50):
                background = 255 if index >= 30 else 0
                frame = np.full((240, 320, 3), background, dtype=np.uint8)
                x = 10 + index * 4
                cv2.rectangle(frame, (x, 80), (min(x + 45, 319), 150), (128, 128, 128), -1)
                writer.write(frame)
        finally:
            writer.release()

        findings, warnings, _frame_count = ai_analytics._analyze_sequence(video_path)
        finding_types = {finding["finding_type"] for finding in findings}
        self.assertIn("motion", finding_types)
        self.assertIn("scene_change", finding_types)
        self.assertNotIn("no_decodable_frames", warnings)
        motion = next(finding for finding in findings if finding["finding_type"] == "motion")
        self.assertEqual(motion["bbox"]["detector"], "opencv_mog2")


if __name__ == "__main__":
    unittest.main()
