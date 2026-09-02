from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from engine.app.core.config import EXPORTS_DIR, FFMPEG_BIN
from engine.app.verification.media_fixture import ensure_playable_h264
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import (
    get_case,
    get_device,
    list_sequences,
    persist_job,
    set_device_drift_offset,
    update_device_identification,
    update_sequence_playable_frame_count,
    verify_device_integrity,
)
from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.parsers.unwrap import NAL_START_3, NAL_START_4, unwrap_to_h264
from engine.app.services.acquisition import acquire_upload, create_lab_specimen, _device_as_evidence
from engine.app.parsers.image_io import evidence_size, read_image_bytes
from engine.app.services.recovery import run_recovery_job, segments_as_legacy
from engine.app.services.timeline import build_timeline_for_device

logger = logging.getLogger("forensic.engine")

FFPROBE_BIN = "ffprobe"


def _count_decoded_frames(video_path: Path) -> int | None:
    if not shutil.which(FFPROBE_BIN):
        return None
    cmd = [
        FFPROBE_BIN,
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_read_frames",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    raw = (result.stdout or "").strip()
    if not raw or raw.upper() == "N/A":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


router = APIRouter(tags=["devices"])


class SyntheticAcquireRequest(BaseModel):
    actor: str = Field(min_length=1)
    source: Literal["synthetic_specimen"] = "synthetic_specimen"
    vendor: Literal["dahua", "honeywell", "hikvision"] = "dahua"


class RecoveryRequest(BaseModel):
    actor: str = Field(min_length=1)
    max_scan_bytes: int | None = None
    adapter: str | None = None


class DriftCalibrationRequest(BaseModel):
    reference_wall_unix: float
    reference_device_unix: float


@router.post("/cases/{case_id}/devices/acquire")
async def acquire_device(
    case_id: str,
    actor: str = Form(...),
    file: UploadFile | None = File(None),
    source: str | None = Form(None),
) -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")

    if source == "synthetic_specimen":
        try:
            return await create_lab_specimen(case_id, actor, vendor="dahua")
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Lab specimen failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if file is None:
        raise HTTPException(status_code=400, detail="file is required for upload acquisition")

    try:
        return await acquire_upload(case_id, actor, file)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Acquire failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cases/{case_id}/devices/acquire/synthetic")
async def acquire_synthetic(case_id: str, body: SyntheticAcquireRequest) -> dict:
    try:
        return await create_lab_specimen(case_id, body.actor, vendor=body.vendor)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Lab specimen failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/devices/{device_id}")
def get_device_detail(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    evidence = _device_as_evidence(device)
    integrity = verify_device_integrity(device_id)
    return {"device": device, "evidence": evidence, "integrity": integrity}


@router.get("/devices/{device_id}/identification")
def get_device_identification(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    path = Path(device["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing on disk")
    if device.get("detection_trace_json"):
        try:
            return json.loads(device["detection_trace_json"])
        except json.JSONDecodeError:
            pass
    report = identify_image(path)
    update_device_identification(device_id, report)
    return report


@router.post("/devices/{device_id}/identification")
def run_device_identification(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    path = Path(device["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing on disk")
    report = identify_image(path)
    update_device_identification(device_id, report)
    return report


@router.get("/devices/{device_id}/structure")
def get_device_structure(device_id: str) -> dict:
    from engine.app.services.device_structure import probe_device_structure

    if not get_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        return probe_device_structure(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/devices/{device_id}/bytes")
def read_device_bytes(device_id: str, offset: int = 0, length: int = 256) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if offset < 0 or length <= 0 or length > 65536:
        raise HTTPException(status_code=400, detail="offset must be >= 0 and 1 <= length <= 65536")
    path = Path(device["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing on disk")
    file_size = evidence_size(path)
    if offset >= file_size:
        raise HTTPException(status_code=400, detail="offset beyond file size")
    read_len = min(length, file_size - offset)
    chunk = read_image_bytes(path, offset, read_len)
    return {
        "device_id": device_id,
        "offset": offset,
        "length": len(chunk),
        "file_size": file_size,
        "hex": chunk.hex(),
        "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in chunk),
    }


def _sequence_payload(seq: dict, device: dict) -> dict:
    return {
        "id": seq["id"],
        "device_id": seq["device_id"],
        "channel": seq.get("channel"),
        "byte_start": seq.get("byte_start"),
        "byte_end": seq.get("byte_end"),
        "byte_length": seq.get("byte_length"),
        "container_units": seq.get("frame_count"),
        "playable_frame_count": seq.get("playable_frame_count"),
        "confidence": seq.get("confidence"),
        "validation_level": seq.get("validation_level"),
        "output_path": seq.get("output_path"),
        "output_md5": seq.get("output_md5"),
        "output_sha256": seq.get("output_sha256"),
        "recovery_job_id": seq.get("recovery_job_id"),
        "recorder_start_ts": seq.get("recorder_start_ts"),
        "recorder_end_ts": seq.get("recorder_end_ts"),
        "corrected_start_ts": seq.get("corrected_start_ts"),
        "corrected_end_ts": seq.get("corrected_end_ts"),
        "timestamp_source": seq.get("timestamp_source"),
        "timestamp_confidence": seq.get("timestamp_confidence"),
        "codec": seq.get("codec"),
        "parser_name": seq.get("parser_name"),
        "parser_version": seq.get("parser_version"),
        "signature_evidence": seq.get("signature_evidence") or {},
        "validation_evidence": seq.get("validation_evidence") or {},
        "vendor": device.get("declared_brand"),
    }


@router.get("/devices/{device_id}/bytes/find")
def find_device_bytes(
    device_id: str,
    q: str = Query(..., min_length=1, max_length=128),
    from_offset: int = 0,
    encoding: Literal["ascii", "hex"] = "ascii",
    max_scan_bytes: int = 16 * 1024 * 1024,
) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if from_offset < 0:
        raise HTTPException(status_code=400, detail="from_offset must be >= 0")
    path = Path(device["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file missing on disk")
    if encoding == "hex":
        try:
            needle = bytes.fromhex(q.replace(" ", ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid hex pattern") from exc
    else:
        needle = q.encode("utf-8")
    if not needle:
        raise HTTPException(status_code=400, detail="Empty search pattern")

    file_size = evidence_size(path)
    if from_offset >= file_size:
        raise HTTPException(status_code=400, detail="from_offset beyond file size")

    chunk_size = 65536
    scanned = 0
    cursor = from_offset
    while cursor < file_size and scanned < max_scan_bytes:
        read_len = min(chunk_size, file_size - cursor, max_scan_bytes - scanned)
        block = read_image_bytes(path, cursor, read_len)
        scanned += len(block)
        hit = block.find(needle)
        if hit >= 0:
            return {
                "device_id": device_id,
                "offset": cursor + hit,
                "length": len(needle),
                "encoding": encoding,
                "pattern": q,
            }
        if len(block) < read_len:
            break
        cursor += max(len(block) - len(needle) + 1, 1)

    return {
        "device_id": device_id,
        "offset": None,
        "length": 0,
        "encoding": encoding,
        "pattern": q,
        "scanned_bytes": scanned,
    }


@router.get("/devices/{device_id}/sequences/{segment_id}")
def get_device_sequence(device_id: str, segment_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    seq = next((s for s in list_sequences(device_id) if s["id"] == segment_id), None)
    if not seq:
        raise HTTPException(status_code=404, detail="Segment not found")
    return _sequence_payload(seq, device)


@router.get("/devices/{device_id}/verify")
def verify_device(device_id: str) -> dict:
    try:
        return verify_device_integrity(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/devices/{device_id}/drift-calibration")
def calibrate_device_drift(device_id: str, body: DriftCalibrationRequest) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    offset = body.reference_wall_unix - body.reference_device_unix
    updated = set_device_drift_offset(device_id, offset)
    return {
        "device_id": device_id,
        "drift_offset_seconds": updated["drift_offset_seconds"],
        "note": "Apply offset when interpreting device-native timestamps on the timeline",
    }


@router.post("/devices/{device_id}/recover")
async def recover_device(
    device_id: str,
    body: RecoveryRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    case_id = device["case_id"]
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")

    job = await job_manager.create("recovery")
    persist_job(
        job.id,
        "recovery",
        "pending",
        result={"case_id": case_id, "device_id": device_id},
    )

    async def _run() -> None:
        await run_recovery_job(
            job.id,
            case_id,
            device_id,
            body.actor,
            max_scan_bytes=body.max_scan_bytes,
            adapter=body.adapter,
        )

    background_tasks.add_task(_run)
    job_row = {
        "id": job.id,
        "case_id": case_id,
        "image_id": device_id,
        "status": "running",
        "vendor": None,
        "adapter": None,
        "stats_json": None,
        "error": None,
        "started_at": job.created_at,
        "completed_at": None,
    }
    return {"job": job_row, "status": "running", "poll_url": f"/api/v1/jobs/{job.id}"}


@router.get("/devices/{device_id}/sequences")
def list_device_sequences(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    segments = segments_as_legacy(device_id, {"job_id": device_id, "vendor": device.get("declared_brand")})
    return {"device_id": device_id, "segments": segments}


@router.get("/devices/{device_id}/timeline")
def device_timeline(device_id: str) -> dict:
    try:
        return build_timeline_for_device(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/devices/{device_id}/sequences/{segment_id}/export")
def export_sequence(
    device_id: str,
    segment_id: str,
    full: int = Query(0, ge=0, le=1),
    from_ms: int | None = Query(None, ge=0),
    to_ms: int | None = Query(None, ge=0),
) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    seq = next((s for s in list_sequences(device_id) if s["id"] == segment_id), None)
    if not seq:
        raise HTTPException(status_code=404, detail="Segment not found")
    if from_ms is not None and to_ms is not None and to_ms <= from_ms:
        raise HTTPException(status_code=400, detail="to_ms must be greater than from_ms")

    artifact_path = Path(seq["output_path"])
    byte_length = seq.get("byte_length")
    if (
        not artifact_path.exists()
        or byte_length is None
        or artifact_path.stat().st_size != int(byte_length)
        or artifact_path.resolve() == Path(device["image_path"]).resolve()
    ):
        raise HTTPException(status_code=409, detail="Sequence does not have a verified bounded artifact")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = EXPORTS_DIR / f"{uuid.uuid4().hex}.h264"
    mp4_path = EXPORTS_DIR / f"{raw_path.stem}.mp4"

    chunk = artifact_path.read_bytes()

    h264 = ensure_playable_h264(unwrap_to_h264(chunk))
    if NAL_START_3 not in h264 and NAL_START_4 not in h264:
        h264 = ensure_playable_h264(chunk)
    raw_path.write_bytes(h264)

    ranged = from_ms is not None and to_ms is not None

    def transcode_to_mp4(source: Path, destination: Path) -> bool:
        if not shutil.which(FFMPEG_BIN):
            return False
        if ranged:
            from_s = from_ms / 1000
            dur_s = (to_ms - from_ms) / 1000
            copy_cmd = [
                FFMPEG_BIN,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{from_s:.3f}",
                "-f",
                "h264",
                "-i",
                str(source),
                "-t",
                f"{dur_s:.3f}",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(destination),
            ]
            result = subprocess.run(copy_cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
                return True
            fallback_cmd = [
                FFMPEG_BIN,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{from_s:.3f}",
                "-f",
                "h264",
                "-i",
                str(source),
                "-t",
                f"{dur_s:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                str(destination),
            ]
            result = subprocess.run(fallback_cmd, capture_output=True, text=True, check=False)
            return result.returncode == 0 and destination.exists() and destination.stat().st_size > 0

        cmd = [
            FFMPEG_BIN,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "h264",
            "-i",
            str(source),
        ]
        if not full:
            cmd.extend(["-vf", "scale='min(1280,iw)':-2"])
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                str(destination),
            ]
        )
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode == 0 and destination.exists() and destination.stat().st_size > 0

    out_path = raw_path
    if transcode_to_mp4(raw_path, mp4_path):
        raw_path.unlink(missing_ok=True)
        out_path = mp4_path
        if not ranged:
            frame_count = _count_decoded_frames(mp4_path)
            if frame_count is not None:
                update_sequence_playable_frame_count(segment_id, frame_count)

    return {
        "filename": out_path.name,
        "download_url": f"/api/v1/files/{out_path.name}",
        "media_type": "video/mp4" if out_path.suffix == ".mp4" else "h264",
    }
