from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from engine.app.core.config import FFMPEG_BIN, YUNET_MODEL_PATH, YOLOX_MODEL_PATH
from engine.app.verification.media_fixture import ensure_playable_h264
from engine.app.parsers.unwrap import unwrap_to_h264
from engine.app.core.db import append_custody, get_db
from engine.app.core.hashing import hash_file
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import (
    delete_ai_findings_for_device,
    get_device,
    insert_ai_finding,
    list_sequences,
    persist_job,
)

logger = logging.getLogger("forensic.engine")

SAMPLE_FPS = 1.0
SCENE_CHANGE_THRESHOLD = 0.18
FOREGROUND_RATIO_THRESHOLD = 0.005
OBJECT_CONFIDENCE_THRESHOLD = 0.35
OBJECT_NMS_THRESHOLD = 0.45
YOLOX_INPUT_SIZE = (416, 416)
YOLOX_VERSION = "0.1.1rc0"

COCO_LABELS = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)

_cv2 = None
_np = None
_cv_checked = False
_yolox_net = None
_yolox_checked = False


def _load_cv() -> bool:
    global _cv2, _np, _cv_checked
    if _cv_checked:
        return _cv2 is not None and _np is not None
    _cv_checked = True
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        if not hasattr(cv2, "VideoCapture") or not hasattr(cv2, "dnn"):
            raise ImportError("OpenCV video or DNN support is unavailable")
        _cv2 = cv2
        _np = np
    except ImportError:
        logger.exception("OpenCV analytics dependencies are unavailable")
    return _cv2 is not None and _np is not None


def _ffmpeg_transcode_path(source: Path) -> Path | None:
    ffmpeg = shutil.which(FFMPEG_BIN)
    if not ffmpeg or not source.exists():
        return None
    destination = source.with_suffix(".analytics.mp4")
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "h264",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
        return destination
    destination.unlink(missing_ok=True)
    return None


def _sampled_frames(video_path: Path) -> Iterator[tuple[int, object]]:
    if not _load_cv():
        return
    cv2 = _cv2
    assert cv2 is not None

    temp_paths: list[Path] = []

    def open_capture(path: Path) -> object | None:
        capture = cv2.VideoCapture(str(path))
        if capture.isOpened():
            return capture
        capture.release()
        return None

    capture = open_capture(video_path)
    if capture is None:
        try:
            playable = ensure_playable_h264(unwrap_to_h264(video_path.read_bytes()))
            temp_h264 = video_path.with_suffix(".playable.h264")
            temp_h264.write_bytes(playable)
            temp_paths.append(temp_h264)
            transcode = _ffmpeg_transcode_path(temp_h264)
            if transcode:
                temp_paths.append(transcode)
                capture = open_capture(transcode)
            if capture is None:
                capture = open_capture(temp_h264)
        except OSError:
            capture = None

    if capture is None:
        for path in temp_paths:
            path.unlink(missing_ok=True)
        return

    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    if source_fps <= 0 or source_fps > 240:
        source_fps = 25.0
    stride = max(1, round(source_fps / SAMPLE_FPS))
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride == 0:
                reported_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0)
                offset_ms = int(reported_ms if reported_ms > 0 else (frame_index / source_fps) * 1000)
                yield offset_ms, frame
            frame_index += 1
    finally:
        capture.release()
        for path in temp_paths:
            path.unlink(missing_ok=True)


def _load_face_detector() -> tuple[str, object] | None:
    if not _load_cv():
        return None
    cv2 = _cv2
    assert cv2 is not None
    if YUNET_MODEL_PATH.exists() and hasattr(cv2, "FaceDetectorYN"):
        detector = cv2.FaceDetectorYN.create(str(YUNET_MODEL_PATH), "", (320, 320), 0.6, 0.3, 5000)
        return "opencv_yunet_2023mar", detector
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None
    detector = cv2.CascadeClassifier(str(cascade_path))
    return None if detector.empty() else ("opencv_haar_frontalface", detector)


def _load_yolox() -> object | None:
    global _yolox_net, _yolox_checked
    if _yolox_checked:
        return _yolox_net
    _yolox_checked = True
    if not YOLOX_MODEL_PATH.exists() or not _load_cv():
        return None
    cv2 = _cv2
    assert cv2 is not None
    try:
        _yolox_net = cv2.dnn.readNetFromONNX(str(YOLOX_MODEL_PATH))
    except Exception:
        logger.exception("Could not load YOLOX model at %s", YOLOX_MODEL_PATH)
        _yolox_net = None
    return _yolox_net


def _yolox_decode(output: object) -> object:
    np = _np
    assert np is not None
    predictions = np.squeeze(output, axis=0)
    grids = []
    expanded_strides = []
    for stride in (8, 16, 32):
        height, width = YOLOX_INPUT_SIZE[0] // stride, YOLOX_INPUT_SIZE[1] // stride
        yv, xv = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
        grid = np.stack((xv, yv), axis=2).reshape(1, -1, 2)
        grids.append(grid)
        expanded_strides.append(np.full((*grid.shape[:2], 1), stride))
    grid = np.concatenate(grids, axis=1).reshape(-1, 2)
    strides = np.concatenate(expanded_strides, axis=1).reshape(-1, 1)
    predictions[:, :2] = (predictions[:, :2] + grid) * strides
    predictions[:, 2:4] = np.exp(predictions[:, 2:4]) * strides
    return predictions


def _detect_objects(frame: object) -> list[tuple[str, float, dict]]:
    net = _load_yolox()
    if net is None:
        return []
    cv2, np = _cv2, _np
    assert cv2 is not None and np is not None
    height, width = frame.shape[:2]  # type: ignore[attr-defined]
    ratio = min(YOLOX_INPUT_SIZE[0] / height, YOLOX_INPUT_SIZE[1] / width)
    resized = cv2.resize(frame, (int(width * ratio), int(height * ratio)))
    padded = np.full((YOLOX_INPUT_SIZE[0], YOLOX_INPUT_SIZE[1], 3), 114, dtype=np.uint8)
    padded[: resized.shape[0], : resized.shape[1]] = resized
    blob = cv2.dnn.blobFromImage(padded, 1.0, YOLOX_INPUT_SIZE, swapRB=True)
    net.setInput(blob)
    predictions = _yolox_decode(net.forward())

    boxes: list[list[int]] = []
    scores: list[float] = []
    class_ids: list[int] = []
    for prediction in predictions:
        class_id = int(np.argmax(prediction[5:]))
        confidence = float(prediction[4] * prediction[5 + class_id])
        if confidence < OBJECT_CONFIDENCE_THRESHOLD:
            continue
        center_x, center_y, box_width, box_height = (float(value) / ratio for value in prediction[:4])
        x = max(0, int(center_x - box_width / 2))
        y = max(0, int(center_y - box_height / 2))
        box = [x, y, max(1, int(box_width)), max(1, int(box_height))]
        boxes.append(box)
        scores.append(confidence)
        class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, scores, OBJECT_CONFIDENCE_THRESHOLD, OBJECT_NMS_THRESHOLD)
    hits: list[tuple[str, float, dict]] = []
    for raw_index in list(indices)[:50]:
        index = int(np.asarray(raw_index).reshape(-1)[0])
        x, y, box_width, box_height = boxes[index]
        class_id = class_ids[index]
        label = COCO_LABELS[class_id] if class_id < len(COCO_LABELS) else f"class_{class_id}"
        hits.append(
            (
                label,
                scores[index],
                {
                    "x": x,
                    "y": y,
                    "w": min(box_width, width - x),
                    "h": min(box_height, height - y),
                    "detector": "yolox_nano",
                    "detector_version": YOLOX_VERSION,
                    "threshold": OBJECT_CONFIDENCE_THRESHOLD,
                    "model_path": YOLOX_MODEL_PATH.name,
                },
            )
        )
    return hits


def _analyze_sequence(video_path: Path) -> tuple[list[dict], list[str], int]:
    if not _load_cv():
        return [], ["opencv_unavailable"], 0
    cv2 = _cv2
    assert cv2 is not None
    subtractor = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=32, detectShadows=True)
    face_detector = _load_face_detector()
    findings: list[dict] = []
    warnings: list[str] = []
    previous_gray = None
    frame_count = 0

    for offset_ms, frame in _sampled_frames(video_path):
        frame_count += 1
        gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
        if previous_gray is not None:
            scene_score = float(cv2.absdiff(previous_gray, gray).mean() / 255.0)
            if scene_score >= SCENE_CHANGE_THRESHOLD:
                findings.append(
                    {
                        "frame_offset_ms": offset_ms,
                        "finding_type": "scene_change",
                        "label": "Scene change candidate",
                        "confidence": min(1.0, scene_score),
                        "bbox": {
                            "detector": "mean_absolute_frame_difference",
                            "threshold": SCENE_CHANGE_THRESHOLD,
                            "sample_fps": SAMPLE_FPS,
                        },
                    }
                )
        previous_gray = gray

        mask = subtractor.apply(frame)
        _, foreground = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        foreground_ratio = float(cv2.countNonZero(foreground) / foreground.size)
        if frame_count > 2 and foreground_ratio >= FOREGROUND_RATIO_THRESHOLD:
            contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            significant = [contour for contour in contours if cv2.contourArea(contour) >= 64]
            if significant:
                x, y, width, height = cv2.boundingRect(cv2.convexHull(cv2.vconcat(significant)))
                findings.append(
                    {
                        "frame_offset_ms": offset_ms,
                        "finding_type": "motion",
                        "label": "Foreground motion candidate",
                        "confidence": min(1.0, foreground_ratio / 0.25),
                        "bbox": {
                            "x": int(x),
                            "y": int(y),
                            "w": int(width),
                            "h": int(height),
                            "detector": "opencv_mog2",
                            "threshold": FOREGROUND_RATIO_THRESHOLD,
                            "sample_fps": SAMPLE_FPS,
                        },
                    }
                )

        if face_detector:
            detector_name, detector = face_detector
            if detector_name.startswith("opencv_yunet"):
                height, width = frame.shape[:2]
                detector.setInputSize((width, height))
                _, faces = detector.detect(frame)
                face_rows = [] if faces is None else faces
                for face in face_rows:
                    x, y, width, height = face[:4]
                    score = float(face[-1])
                    confidence = max(0.0, min(1.0, score))
                    findings.append(
                        {
                            "frame_offset_ms": offset_ms,
                            "finding_type": "face",
                            "label": "Face candidate",
                            "confidence": confidence,
                            "bbox": {
                                "x": int(x),
                                "y": int(y),
                                "w": int(width),
                                "h": int(height),
                                "detector": detector_name,
                                "threshold": 0.6,
                                "sample_fps": SAMPLE_FPS,
                            },
                        }
                    )
            else:
                full_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(full_gray, scaleFactor=1.08, minNeighbors=4, minSize=(24, 24))
                for x, y, width, height in faces:
                    findings.append(
                        {
                            "frame_offset_ms": offset_ms,
                            "finding_type": "face",
                            "label": "Face candidate",
                            "confidence": 0.68,
                            "bbox": {
                                "x": int(x),
                                "y": int(y),
                                "w": int(width),
                                "h": int(height),
                                "detector": detector_name,
                                "sample_fps": SAMPLE_FPS,
                            },
                        }
                    )

        for label, confidence, bbox in _detect_objects(frame):
            findings.append(
                {
                    "frame_offset_ms": offset_ms,
                    "finding_type": "object",
                    "label": f"{label} candidate",
                    "confidence": confidence,
                    "bbox": bbox,
                }
            )

    if frame_count == 0:
        warnings.append("no_decodable_frames")
    if not YUNET_MODEL_PATH.exists():
        warnings.append("yunet_model_unavailable_haar_fallback")
    if not YOLOX_MODEL_PATH.exists():
        warnings.append("yolox_model_unavailable")
    return findings, warnings, frame_count


async def _execute_ai_analytics(job_id: str, case_id: str, device_id: str, actor: str) -> None:
    message = "Starting offline analytics at 1 frame per second"
    await job_manager.update(job_id, status="running", progress=0, message=message)
    persist_job(
        job_id,
        "ai_analytics",
        "running",
        case_id=case_id,
        device_id=device_id,
        progress=0,
        message=message,
    )

    device = get_device(device_id)
    if not device:
        error = "Device not found"
        await job_manager.update(job_id, status="failed", error=error)
        persist_job(job_id, "ai_analytics", "failed", case_id=case_id, device_id=device_id, error=error)
        return

    sequences = list_sequences(device_id)
    if not sequences:
        error = "No recovered sequences to analyze"
        await job_manager.update(job_id, status="failed", error=error)
        persist_job(job_id, "ai_analytics", "failed", case_id=case_id, device_id=device_id, error=error)
        return

    delete_ai_findings_for_device(device_id)
    created = 0
    warnings: list[str] = []
    decoded_frames = 0

    if not _load_cv():
        result = {
            "case_id": case_id,
            "device_id": device_id,
            "findings_count": 0,
            "demo_mode_unavailable": True,
            "message": "OpenCV/decodable video unavailable on this host — analytics skipped",
            "warnings": ["opencv_unavailable"],
            "investigative_leads_only": True,
        }
        with get_db() as conn:
            append_custody(
                conn,
                actor=actor,
                action="ai_analytics_skipped_unavailable",
                target_type="case",
                target_id=case_id,
            )
        message = result["message"]
        await job_manager.update(job_id, status="completed", progress=100, message=message, result=result)
        persist_job(
            job_id,
            "ai_analytics",
            "completed",
            case_id=case_id,
            device_id=device_id,
            progress=100,
            message=message,
            result=result,
        )
        return

    for index, sequence in enumerate(sequences):
        progress = min(95.0, ((index + 1) / len(sequences)) * 95)
        artifact = Path(sequence["output_path"])
        expected_length = sequence.get("byte_length")
        if not artifact.exists() or expected_length is None or artifact.stat().st_size != int(expected_length):
            error = f"Sequence {sequence['id']} does not have a bounded artifact"
            await job_manager.update(job_id, status="failed", error=error)
            persist_job(job_id, "ai_analytics", "failed", case_id=case_id, device_id=device_id, error=error)
            return
        actual_md5, actual_sha256 = await asyncio.to_thread(hash_file, artifact)
        if actual_sha256 != sequence["output_sha256"] or actual_md5 != sequence["output_md5"]:
            error = f"Sequence {sequence['id']} failed artifact integrity verification"
            await job_manager.update(job_id, status="failed", error=error)
            persist_job(job_id, "ai_analytics", "failed", case_id=case_id, device_id=device_id, error=error)
            return

        sequence_findings, sequence_warnings, frame_count = await asyncio.to_thread(_analyze_sequence, artifact)
        warnings.extend(f"{sequence['id']}:{warning}" for warning in sequence_warnings)
        decoded_frames += frame_count
        for finding in sequence_findings:
            insert_ai_finding(sequence["id"], **finding)
            created += 1
        await job_manager.update(
            job_id,
            progress=progress,
            message=f"Analyzed sequence {index + 1}/{len(sequences)} · {created} leads",
        )

    demo_unavailable = decoded_frames == 0 and created == 0
    result = {
        "case_id": case_id,
        "device_id": device_id,
        "findings_count": created,
        "finding_types": ["motion", "scene_change", "face", "object"],
        "sample_fps": SAMPLE_FPS,
        "warnings": sorted(set(warnings)),
        "investigative_leads_only": True,
    }
    if demo_unavailable:
        result["demo_mode_unavailable"] = True
        result["message"] = "No decodable video frames on recovered artifacts — analytics produced no leads"
    with get_db() as conn:
        append_custody(
            conn,
            actor=actor,
            action="ai_analytics_completed_with_warnings" if warnings else "ai_analytics_completed",
            target_type="case",
            target_id=case_id,
        )
    message = result.get("message") or f"Offline analytics complete — {created} investigative lead(s)"
    await job_manager.update(job_id, status="completed", progress=100, message=message, result=result)
    persist_job(
        job_id,
        "ai_analytics",
        "completed",
        case_id=case_id,
        device_id=device_id,
        progress=100,
        message=message,
        result=result,
    )


async def run_ai_analytics_job(job_id: str, case_id: str, device_id: str, actor: str) -> None:
    try:
        await _execute_ai_analytics(job_id, case_id, device_id, actor)
    except Exception as exc:
        logger.exception("Offline analytics job %s failed", job_id)
        error = f"Analytics failed: {exc}"
        await job_manager.update(job_id, status="failed", error=error)
        persist_job(
            job_id,
            "ai_analytics",
            "failed",
            case_id=case_id,
            device_id=device_id,
            error=error,
        )
