from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from pramaan.config import EXPORTS_DIR
from pramaan.core import cases as case_store
from pramaan.modules.analysis.export import export_segment

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/jobs/{job_id}/segments/{segment_id}/export")
def export_segment_route(job_id: str, segment_id: str) -> dict:
    job = case_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    segments = case_store.list_segments(job_id)
    segment = next((s for s in segments if s["id"] == segment_id), None)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    evidence_list = case_store.list_evidence(job["case_id"])
    image = next((e for e in evidence_list if e["id"] == job["image_id"]), None)
    if not image:
        raise HTTPException(status_code=404, detail="Source image not found")

    out = export_segment(
        Path(image["storage_path"]),
        segment["offset_start"],
        segment["offset_end"],
        segment["vendor"],
    )
    case_store.append_custody(
        job["case_id"],
        "system",
        "segment_exported",
        f"{out.name} · segment {segment_id}",
        image_id=job["image_id"],
    )
    return {"filename": out.name, "download_url": f"/api/exports/{out.name}"}
