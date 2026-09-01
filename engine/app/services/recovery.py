from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from engine.app.core.config import APP_VERSION
from engine.app.core.db import append_custody, get_db
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import (
    case_storage_dir,
    get_device,
    insert_sequence,
    list_sequences,
    persist_job,
)
from engine.app.core.hashing import hash_file
from engine.app.parsers.manufacturer_detect import detect_vendors
from engine.app.parsers.registry import bootstrap_defaults, get

logger = logging.getLogger("forensic.engine")
COPY_CHUNK_SIZE = 1024 * 1024


def _write_bounded_artifact(
    source: Path,
    destination: Path,
    byte_start: int,
    byte_end: int,
) -> tuple[str, str]:
    source_size = source.stat().st_size
    if byte_start < 0 or byte_end <= byte_start or byte_end > source_size:
        raise ValueError(f"Invalid recovered byte range [{byte_start}, {byte_end}) for {source_size}-byte source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    remaining = byte_end - byte_start
    with source.open("rb") as src, destination.open("wb") as dst:
        src.seek(byte_start)
        while remaining:
            chunk = src.read(min(COPY_CHUNK_SIZE, remaining))
            if not chunk:
                raise OSError("Evidence source ended before recovered range was copied")
            dst.write(chunk)
            remaining -= len(chunk)
    return hash_file(destination)


def _confidence_label(value: float, validation: str) -> str:
    if validation in {"dual_signature_4", "dual_signature"} and value >= 0.85:
        return "high"
    if validation in {"hkvi_block_4", "hkvi_block"} and value >= 0.8:
        return "high"
    if validation in {"honeywell_index_4", "honeywell_format_carve_4", "filesystem_deleted_inode"}:
        return "high"
    if validation in {"honeywell_expired_index", "honeywell_index", "header_footer_only", "hkvi_header_only", "header-only candidate", "filesystem_unallocated"}:
        return "medium"
    if validation == "offset-ordered, timestamp unverified":
        return "low"
    return "low"


async def run_recovery_job(
    job_id: str,
    case_id: str,
    device_id: str,
    actor: str,
    *,
    max_scan_bytes: int | None = None,
    gap_multiplier: float = 2.0,
    min_sequence_frames: int = 10,
) -> None:
    await job_manager.update(job_id, status="running", progress=1, message="Initializing recovery")
    persist_job(
        job_id,
        "recovery",
        "running",
        case_id=case_id,
        device_id=device_id,
        progress=1,
        message="Initializing recovery",
    )

    device = get_device(device_id)
    if not device:
        await job_manager.update(job_id, status="failed", error="Device not found")
        persist_job(
            job_id,
            "recovery",
            "failed",
            case_id=case_id,
            device_id=device_id,
            error="Device not found",
        )
        return

    image_path = Path(device["image_path"])
    if not image_path.exists():
        await job_manager.update(job_id, status="failed", error="Evidence file missing on disk")
        persist_job(
            job_id,
            "recovery",
            "failed",
            case_id=case_id,
            device_id=device_id,
            error="Evidence file missing on disk",
        )
        return

    with get_db() as conn:
        append_custody(
            conn,
            actor=actor,
            action="recovery_started",
            target_type="case",
            target_id=case_id,
        )

    try:
        bootstrap_defaults()
        vendors = detect_vendors(image_path)
        adapter_key = vendors[0].adapter if vendors else "h264_carve"
        adapter = get(adapter_key)
        if not adapter:
            raise RuntimeError(f"Adapter not registered: {adapter_key}")

        await job_manager.update(job_id, progress=10, message=f"Scanning with {adapter_key}")
        segments = await asyncio.to_thread(adapter.scan, image_path, max_bytes=max_scan_bytes)

        stored = 0
        evidence_rows: list[dict] = []
        artifact_dir = case_storage_dir(case_id) / "sequences"
        for seq_index, seg in enumerate(sorted(segments, key=lambda item: item.offset_start)):
            if seg.offset_end <= seg.offset_start:
                continue
            suffix = ".h264" if seg.codec == "h264" else ".bin"
            artifact_path = artifact_dir / f"{job_id}_{seq_index:06d}{suffix}"
            output_md5, output_sha256 = await asyncio.to_thread(
                _write_bounded_artifact,
                image_path,
                artifact_path,
                seg.offset_start,
                seg.offset_end,
            )
            conf = _confidence_label(seg.confidence, seg.validation)
            row = insert_sequence(
                device_id,
                channel=int(seg.channel or 0),
                start_ts_raw=seg.recorder_start_ts,
                end_ts_raw=seg.recorder_end_ts,
                confidence=conf,
                validation_level=seg.validation,
                output_path=str(artifact_path),
                output_md5=output_md5,
                output_sha256=output_sha256,
                frame_count=seg.frame_count,
                drift_offset=float(device.get("drift_offset_seconds") or 0),
                byte_start=seg.offset_start,
                byte_end=seg.offset_end,
                codec=seg.codec,
                offset_order=seq_index,
                timestamp_source=seg.timestamp_source,
                timestamp_confidence=seg.timestamp_confidence,
                parser_name=seg.parser_name,
                parser_version=seg.parser_version,
                recovery_job_id=job_id,
                signature_evidence=seg.signature_evidence,
                validation_evidence=seg.validation_evidence,
            )
            stored += 1
            evidence_rows.append(
                {
                    "sequence_id": row["id"],
                    "byte_start": seg.offset_start,
                    "byte_end": seg.offset_end,
                    "byte_length": seg.offset_end - seg.offset_start,
                    "parser_name": seg.parser_name,
                    "parser_version": seg.parser_version,
                    "signature_evidence": seg.signature_evidence,
                    "validation_evidence": seg.validation_evidence,
                }
            )
            with get_db() as conn:
                append_custody(
                    conn,
                    actor=actor,
                    action="sequence_artifact_created",
                    target_type="case",
                    target_id=case_id,
                    evidence_digest=f"sha256:{output_sha256}",
                )
            progress = 10 + (80 * (seq_index + 1) / max(len(segments), 1))
            await job_manager.update(job_id, progress=progress, message=f"Sequenced {stored} segments")

        result = {
            "case_id": case_id,
            "device_id": device_id,
            "segments_found": stored,
            "adapter": adapter_key,
            "vendor": vendors[0].vendor if vendors else "Generic",
            "app_version": APP_VERSION,
            "evidence": evidence_rows,
        }
        await job_manager.update(job_id, status="completed", progress=100, message="Recovery complete", result=result)
        persist_job(
            job_id,
            "recovery",
            "completed",
            case_id=case_id,
            device_id=device_id,
            progress=100,
            result=result,
        )

        with get_db() as conn:
            append_custody(
                conn,
                actor=actor,
                action="recovery_completed",
                target_type="case",
                target_id=case_id,
            )
    except Exception as exc:
        logger.exception("Recovery job %s failed", job_id)
        await job_manager.update(job_id, status="failed", error=str(exc))
        persist_job(
            job_id,
            "recovery",
            "failed",
            case_id=case_id,
            device_id=device_id,
            error=str(exc),
        )
        with get_db() as conn:
            append_custody(
                conn,
                actor=actor,
                action="recovery_failed",
                target_type="case",
                target_id=case_id,
            )


def segments_as_legacy(device_id: str, job_meta: dict | None = None) -> list[dict]:
    sequences = list_sequences(device_id)
    legacy = []
    for index, seq in enumerate(sequences):
        legacy.append(
            {
                "id": seq["id"],
                "job_id": seq.get("recovery_job_id") or (job_meta.get("job_id") if job_meta else device_id),
                "channel": seq["channel"],
                "vendor": job_meta.get("vendor", "Unknown") if job_meta else "Unknown",
                "offset_start": seq.get("byte_start"),
                "offset_end": seq.get("byte_end"),
                "byte_length": seq.get("byte_length"),
                "frame_count": seq["frame_count"],
                "confidence": _confidence_score(seq["confidence"], seq["validation_level"]),
                "validation": seq["validation_level"],
                "confidence_tier": seq["confidence"],
                "preview_path": None,
                "created_at": seq.get("corrected_start_ts"),
                "recorder_start_ts": seq.get("recorder_start_ts"),
                "recorder_end_ts": seq.get("recorder_end_ts"),
                "corrected_start_ts": seq.get("corrected_start_ts"),
                "corrected_end_ts": seq.get("corrected_end_ts"),
                "timestamp_source": seq.get("timestamp_source"),
                "timestamp_confidence": seq.get("timestamp_confidence"),
                "offset_order": seq.get("offset_order"),
                "codec": seq.get("codec"),
                "parser_name": seq.get("parser_name"),
                "parser_version": seq.get("parser_version"),
                "signature_evidence": seq.get("signature_evidence", {}),
                "validation_evidence": seq.get("validation_evidence", {}),
            }
        )
    return legacy


def _confidence_score(tier: str, validation_level: str) -> float:
    if tier == "high" or validation_level in {"dual_signature_4", "hkvi_block_4"}:
        return 0.92
    if tier == "medium" or validation_level in {"header_footer_only", "hkvi_header_only"}:
        return 0.7
    return 0.55


