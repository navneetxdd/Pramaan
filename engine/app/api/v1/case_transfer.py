from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.core.config import BUNDLES_DIR, MAX_UPLOAD_BYTES
from engine.app.core.db import append_custody, get_db
from engine.app.core.repository import get_case
from engine.app.services.case_bundle import export_case_bundle, import_case_bundle

router = APIRouter(tags=["case-transfer"])


class ImportCaseResponse(BaseModel):
    case_id: str
    files_verified: int
    integrity_ok: bool
    signer_fingerprint: str


@router.post("/cases/{case_id}/export")
def export_case(case_id: str, actor: str = Form(...)) -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        bundle_path = export_case_bundle(case_id, actor.strip())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with get_db() as conn:
        append_custody(
            conn,
            actor=actor.strip(),
            action="case_exported",
            target_type="case",
            target_id=case_id,
        )

    filename = bundle_path.name
    return {
        "case_id": case_id,
        "filename": filename,
        "download_url": f"/api/v1/bundles/{filename}",
        "size_bytes": bundle_path.stat().st_size,
    }


@router.get("/bundles/{filename}")
def download_bundle(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (BUNDLES_DIR / filename).resolve()
    if not str(path).startswith(str(BUNDLES_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bundle not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.post("/cases/import", response_model=ImportCaseResponse)
async def import_case(actor: str = Form(...), bundle: UploadFile = File(...)) -> ImportCaseResponse:
    if not bundle.filename:
        raise HTTPException(status_code=400, detail="Bundle filename required")

    temp_path = BUNDLES_DIR / f"upload_{uuid.uuid4().hex}.pramaan.zip"
    total = 0
    try:
        with temp_path.open("wb") as handle:
            while True:
                chunk = await bundle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Bundle exceeds configured upload limit")
                handle.write(chunk)

        result = import_case_bundle(temp_path, actor.strip())
        return ImportCaseResponse(
            case_id=result["case_id"],
            files_verified=result["files_verified"],
            integrity_ok=result["integrity_ok"],
            signer_fingerprint=result["signer_fingerprint"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
