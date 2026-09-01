from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from pramaan.core import cases as case_store
from pramaan.modules.acquisition.service import acquire_disk_image
from pramaan.modules.custody.hash_chain import verify_chain
from pramaan.modules.recovery.service import execute_recovery_job, schedule_recovery
from pramaan.schemas.case import CaseCreate
from pramaan.schemas.recovery import RecoveryRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["pramaan"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "pramaan"}


@router.get("/cases")
def list_cases() -> dict:
    return {"cases": case_store.list_cases()}


@router.post("/cases")
def create_case(body: CaseCreate) -> dict:
    case = case_store.create_case(body.title, body.examiner, body.reference)
    return {"case": case}


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "case": case,
        "evidence": case_store.list_evidence(case_id),
        "jobs": case_store.list_jobs_for_case(case_id),
        "custody": case_store.list_custody(case_id),
    }


@router.post("/cases/{case_id}/acquire")
async def acquire(case_id: str, actor: str = Form(...), file: UploadFile = File(...)) -> dict:
    try:
        return await acquire_disk_image(case_id, actor, file)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Acquire failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cases/{case_id}/evidence/{image_id}/recover")
def recover(
    case_id: str,
    image_id: str,
    body: RecoveryRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    scheduled = schedule_recovery(case_id, image_id, body.actor, max_scan_bytes=body.max_scan_bytes)
    job = scheduled["job"]

    def _run() -> None:
        try:
            execute_recovery_job(
                job["id"],
                case_id,
                image_id,
                body.actor,
                max_scan_bytes=body.max_scan_bytes,
            )
        except Exception:
            pass

    background_tasks.add_task(_run)
    return {"job": job, "status": "running", "poll_url": f"/api/jobs/{job['id']}"}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = case_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job, "segments": case_store.list_segments(job_id)}


@router.get("/cases/{case_id}/custody")
def custody(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    events = case_store.list_custody(case_id)
    return {"events": events, "chain": verify_chain(sorted(events, key=lambda e: e["id"]), case_id)}


@router.get("/evidence/{image_id}/verify")
def verify(image_id: str) -> dict:
    try:
        return case_store.verify_image_integrity(image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
