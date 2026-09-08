from __future__ import annotations

import unittest

from engine.app.services.ai_analytics import (
    INVESTIGATIVE_OBJECT_LABELS,
    OBJECT_CONFIDENCE_THRESHOLD,
    _cap_object_findings,
)


class FindingsNoiseFloorTests(unittest.TestCase):
    """D24: object findings must not bury real leads under COCO kitchen classes
    or hundreds of near-duplicate boxes."""

    def test_kitchen_and_household_coco_classes_are_excluded(self) -> None:
        for junk in ("wine glass", "bowl", "clock", "vase", "teddy bear", "toilet"):
            self.assertNotIn(junk, INVESTIGATIVE_OBJECT_LABELS)

    def test_investigative_classes_are_kept(self) -> None:
        for keep in ("person", "car", "truck", "backpack", "knife"):
            self.assertIn(keep, INVESTIGATIVE_OBJECT_LABELS)

    def test_object_confidence_floor_is_not_permissive(self) -> None:
        self.assertGreaterEqual(OBJECT_CONFIDENCE_THRESHOLD, 0.45)

    def test_cap_keeps_strongest_objects_and_leaves_other_types(self) -> None:
        findings = [{"finding_type": "motion", "confidence": 0.1}]
        findings += [
            {"finding_type": "object", "confidence": c / 100}
            for c in range(1, 61)  # 60 object findings
        ]
        findings.append({"finding_type": "face", "confidence": 0.9})

        capped, was_capped = _cap_object_findings(findings, limit=40)

        self.assertTrue(was_capped)
        kept_objects = [f for f in capped if f["finding_type"] == "object"]
        self.assertEqual(len(kept_objects), 40)
        # the 40 strongest (0.21..0.60) survive; the weakest 20 are dropped
        self.assertEqual(min(f["confidence"] for f in kept_objects), 0.21)
        # non-object findings are untouched and keep their positions
        self.assertEqual(capped[0]["finding_type"], "motion")
        self.assertEqual(capped[-1]["finding_type"], "face")

    def test_cap_is_a_noop_below_the_limit(self) -> None:
        findings = [{"finding_type": "object", "confidence": 0.5}] * 10
        capped, was_capped = _cap_object_findings(findings, limit=40)
        self.assertFalse(was_capped)
        self.assertEqual(len(capped), 10)


if __name__ == "__main__":
    unittest.main()
