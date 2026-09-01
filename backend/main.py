from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pramaan import __version__
from pramaan.analysis.export import build_case_report, export_segment_h264
from pramaan.api.routes import router
from pramaan.config import EXPORTS_DIR
from pramaan.core import cases as case_store
from pramaan.core.database import init_db

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="Pramaan", version=__version__, description="DVR/NVR forensic analysis")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/cases/{case_id}/report")
def case_report(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_case_report(
        case,
        case_store.list_evidence(case_id),
        case_store.list_jobs_for_case(case_id),
        case_store.list_custody(case_id),
    )


@app.post("/api/jobs/{job_id}/segments/{segment_id}/export")
def export_segment(job_id: str, segment_id: str) -> dict:
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

    out = export_segment_h264(
        Path(image["storage_path"]),
        segment["offset_start"],
        segment["offset_end"],
    )
    return {"filename": out.name, "download_url": f"/api/exports/{out.name}"}


@app.get("/api/exports/{filename}")
def download_export(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (EXPORTS_DIR / filename).resolve()
    if not str(path).startswith(str(EXPORTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    media = "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"
    return FileResponse(path, filename=path.name, media_type=media)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            raise HTTPException(status_code=503, detail="Frontend not built")
        return FileResponse(index)
