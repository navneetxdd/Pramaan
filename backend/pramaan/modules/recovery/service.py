from __future__ import annotations

import logging
from pathlib import Path

from pramaan.core import cases as case_store
from pramaan.recovery.adapters.dahua_dhav import detect_vendors
from pramaan.modules.recovery.registry import bootstrap_defaults, get

logger = logging.getLogger(__name__)


def execute_recovery_job(
    job_id: str,
    case_id: str,
    image_id: str,
    actor: str,
    *,
    max_scan_bytes: int | None = None,
) -> dict:
    bootstrap_defaults()

    evidence_list = case_store.list_evidence(case_id)
    image = next((item for item in evidence_list if item["id"] == image_id), None)
    if not image:
        raise ValueError("Evidence image not found for case")

    image_path = Path(image["storage_path"])
    if not image_path.exists():
        raise FileNotFoundError("Evidence file missing on disk")

    vendors = detect_vendors(image_path)
    adapter_key = vendors[0].adapter if vendors else "h264_carve"
    adapter = get(adapter_key)
    if not adapter:
        raise RuntimeError(f"Adapter not registered: {adapter_key}")

    case_store.append_custody(
        case_id,
        actor,
        "recovery_started",
        f"Job {job_id} on {image['filename']}",
        image_id=image_id,
    )

    try:
        segments = adapter.scan(image_path, max_bytes=max_scan_bytes)
        for seg in segments:
            case_store.insert_segment(
                job_id,
                channel=seg.channel,
                vendor=seg.vendor,
                offset_start=seg.offset_start,
                offset_end=seg.offset_end,
                frame_count=seg.frame_count,
                confidence=seg.confidence,
                validation=seg.validation,
            )
        stats = {
            "segments_found": len(segments),
            "bytes_scanned": (
                image_path.stat().st_size
                if max_scan_bytes is None
                else min(max_scan_bytes, image_path.stat().st_size)
            ),
            "vendor_hits": [
                {
                    "vendor": hit.vendor,
                    "adapter": hit.adapter,
                    "confidence": hit.confidence,
                    "markers": hit.markers,
                }
                for hit in vendors
            ],
        }
        case_store.complete_recovery_job(
            job_id,
            status="completed",
            vendor=vendors[0].vendor if vendors else "Generic",
            adapter=adapter_key,
            stats=stats,
        )
        case_store.append_custody(
            case_id,
            actor,
            "recovery_completed",
            f"{len(segments)} segments · adapter {adapter_key}",
            image_id=image_id,
        )
        logger.info("Recovery job %s completed: %d segments", job_id, len(segments))
        return {
            "job": case_store.get_job(job_id),
            "segments": case_store.list_segments(job_id),
            "vendors": stats["vendor_hits"],
        }
    except Exception as exc:
        case_store.complete_recovery_job(
            job_id,
            status="failed",
            vendor=None,
            adapter=adapter_key,
            stats={"segments_found": 0},
            error=str(exc),
        )
        case_store.append_custody(case_id, actor, "recovery_failed", str(exc), image_id=image_id)
        logger.exception("Recovery job %s failed", job_id)
        raise


def schedule_recovery(
    case_id: str,
    image_id: str,
    actor: str,
    *,
    max_scan_bytes: int | None = None,
) -> dict:
    job = case_store.create_recovery_job(case_id, image_id)
    return {
        "job": job,
        "case_id": case_id,
        "image_id": image_id,
        "actor": actor,
        "max_scan_bytes": max_scan_bytes,
    }
