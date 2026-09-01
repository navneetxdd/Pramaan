from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from pramaan.config import CASES_DIR, MAX_UPLOAD_BYTES
from pramaan.core import cases as case_store
from pramaan.recovery.adapters.dahua_dhav import detect_vendors
from pramaan.recovery.pipeline import run_recovery

router = APIRouter(prefix="/api", tags=["pramaan"])


class CreateCaseBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    examiner: str = Field(min_length=2, max_length=120)
    reference: str | None = Field(default=None, max_length=120)


class RecoveryBody(BaseModel):
    actor: str = Field(min_length=2, max_length=120)
    max_scan_bytes: int | None = Field(default=None, ge=1024)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "pramaan"}


@router.get("/cases")
def list_cases() -> dict:
    return {"cases": case_store.list_cases()}


@router.post("/cases")
def create_case(body: CreateCaseBody) -> dict:
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
async def acquire_evidence(
    case_id: str,
    actor: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    dest = case_dir / file.filename

    size = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Upload exceeds configured limit")
            handle.write(chunk)

    evidence = case_store.register_evidence(case_id, file.filename, dest, actor.strip())
    vendors = detect_vendors(dest)
    return {"evidence": evidence, "vendor_hints": [hit.__dict__ for hit in vendors]}


@router.post("/cases/{case_id}/evidence/{image_id}/recover")
def recover(case_id: str, image_id: str, body: RecoveryBody) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        return run_recovery(case_id, image_id, body.actor, max_scan_bytes=body.max_scan_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    return {"events": case_store.list_custody(case_id)}


@router.get("/evidence/{image_id}/verify")
def verify(image_id: str) -> dict:
    try:
        return case_store.verify_image_integrity(image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
