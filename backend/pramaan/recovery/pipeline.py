from __future__ import annotations

from pathlib import Path

from pramaan.core import cases as case_store
from pramaan.recovery.adapters.dahua_dhav import DahuaDhavAdapter, detect_vendors
from pramaan.recovery.adapters.h264_carve import H264CarveAdapter
from pramaan.recovery.adapters.hikvision import HikvisionAdapter
from pramaan.recovery.base import RecoveredSegment

ADAPTERS = {
    "dahua_dhav": DahuaDhavAdapter(),
    "hikvision": HikvisionAdapter(),
    "h264_carve": H264CarveAdapter(),
}


def run_recovery(case_id: str, image_id: str, actor: str, *, max_scan_bytes: int | None = None) -> dict:
    evidence_list = case_store.list_evidence(case_id)
    image = next((item for item in evidence_list if item["id"] == image_id), None)
    if not image:
        raise ValueError("Evidence image not found for case")

    image_path = Path(image["storage_path"])
    if not image_path.exists():
        raise FileNotFoundError("Evidence file missing on disk")

    vendors = detect_vendors(image_path)
    job = case_store.create_recovery_job(case_id, image_id)
    case_store.append_custody(
        case_id,
        actor,
        "recovery_started",
        f"Job {job['id']} on {image['filename']}",
        image_id=image_id,
    )

    adapter_key = vendors[0].adapter if vendors else "h264_carve"
    adapter = ADAPTERS[adapter_key]
    try:
        segments = adapter.scan(image_path, max_bytes=max_scan_bytes)
        for seg in segments:
            case_store.insert_segment(
                job["id"],
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
            "bytes_scanned": image_path.stat().st_size if max_scan_bytes is None else min(max_scan_bytes, image_path.stat().st_size),
            "vendor_hits": [
                {"vendor": hit.vendor, "adapter": hit.adapter, "confidence": hit.confidence, "markers": hit.markers}
                for hit in vendors
            ],
        }
        case_store.complete_recovery_job(
            job["id"],
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
        return {
            "job": case_store.get_job(job["id"]),
            "segments": case_store.list_segments(job["id"]),
            "vendors": stats["vendor_hits"],
        }
    except Exception as exc:
        case_store.complete_recovery_job(
            job["id"],
            status="failed",
            vendor=None,
            adapter=adapter_key,
            stats={"segments_found": 0},
            error=str(exc),
        )
        case_store.append_custody(
            case_id,
            actor,
            "recovery_failed",
            str(exc),
            image_id=image_id,
        )
        raise


def preview_segment_bytes(image_path: Path, segment: RecoveredSegment | dict, max_bytes: int = 512 * 1024) -> bytes:
    start = segment["offset_start"] if isinstance(segment, dict) else segment.offset_start
    end = segment["offset_end"] if isinstance(segment, dict) else segment.offset_end
    length = min(end - start, max_bytes)
    with image_path.open("rb") as handle:
        handle.seek(start)
        return handle.read(length)
