#!/usr/bin/env python3
"""Run reproducible event-level analytics checks on the licensed CAVIAR subset."""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.app.services.ai_analytics import SAMPLE_FPS, _analyze_sequence  # noqa: E402

VIDEO = ROOT / "validation_data" / "external" / "caviar" / "Walk1.mpg"
GROUND_TRUTH = ROOT / "validation_data" / "external" / "caviar" / "wk1gt.xml"
RESULT_PATH = ROOT / "validation_data" / "results" / "analytics_validation.json"
SOURCE_FPS = 25


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _sampled_truth() -> tuple[set[int], set[int]]:
    root = ET.parse(GROUND_TRUTH).getroot()
    person_frames: set[int] = set()
    moving_frames: set[int] = set()
    sample_stride = round(SOURCE_FPS / SAMPLE_FPS)
    for frame in root.findall("frame"):
        frame_number = int(frame.attrib["number"])
        if frame_number % sample_stride != 0:
            continue
        if frame.find("./objectlist/object") is not None:
            person_frames.add(frame_number)
        if any((node.text or "").strip().lower() == "moving" for node in frame.findall(".//situation")):
            moving_frames.add(frame_number)
    return person_frames, moving_frames


def _prediction_frames(findings: list[dict], finding_type: str, label_prefix: str | None = None) -> set[int]:
    frames: set[int] = set()
    for finding in findings:
        if finding["finding_type"] != finding_type:
            continue
        if label_prefix and not str(finding.get("label", "")).lower().startswith(label_prefix):
            continue
        frame_number = round((int(finding["frame_offset_ms"]) / 1000) * SOURCE_FPS)
        frames.add(frame_number)
    return frames


def _metrics(expected: set[int], predicted: set[int]) -> dict:
    tolerance = round(SOURCE_FPS / SAMPLE_FPS)
    matched_expected: set[int] = set()
    true_positive_predictions = 0
    for prediction in predicted:
        candidates = [frame for frame in expected - matched_expected if abs(frame - prediction) <= tolerance]
        if candidates:
            matched_expected.add(min(candidates, key=lambda frame: abs(frame - prediction)))
            true_positive_predictions += 1
    false_positives = len(predicted) - true_positive_predictions
    false_negatives = len(expected) - len(matched_expected)
    precision = true_positive_predictions / (true_positive_predictions + false_positives) if predicted else 0.0
    recall = true_positive_predictions / (true_positive_predictions + false_negatives) if expected else 0.0
    return {
        "true_positives": true_positive_predictions,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "event_tolerance_frames": tolerance,
    }


def main() -> int:
    if not VIDEO.exists() or not GROUND_TRUTH.exists():
        print("CAVIAR assets are absent. Run: python scripts/validation/fetch_validation_assets.py --surveillance")
        return 2

    findings, warnings = _analyze_sequence(VIDEO)
    person_truth, moving_truth = _sampled_truth()
    person_predictions = _prediction_frames(findings, "object", "person")
    motion_predictions = _prediction_frames(findings, "motion")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "CAVIAR Walk1",
            "source": "https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/",
            "license": "CC BY-SA; acknowledge EC Funded CAVIAR project/IST 2001 37540",
            "video_sha256": _sha256(VIDEO),
            "ground_truth_sha256": _sha256(GROUND_TRUTH),
        },
        "configuration": {"sample_fps": SAMPLE_FPS, "source_fps": SOURCE_FPS},
        "object_person_event_metrics": _metrics(person_truth, person_predictions),
        "foreground_motion_event_metrics": _metrics(moving_truth, motion_predictions),
        "finding_counts": {
            finding_type: sum(1 for finding in findings if finding["finding_type"] == finding_type)
            for finding_type in ("motion", "scene_change", "face", "object")
        },
        "warnings": warnings,
        "scope": (
            "Single-clip event-level regression. Person boxes supervise person-object events; CAVIAR 'moving' "
            "situations are used as a coarse foreground-motion proxy. Face and scene-change outputs lack ground truth "
            "in this clip and are counts only. Findings remain investigative leads."
        ),
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
