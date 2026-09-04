from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engine.app.core.job_manager import job_manager
from engine.app.core.repository import get_case, persist_job
from engine.app.services import cross_camera

router = APIRouter(tags=["cross-camera"])


class CorrelateRequest(BaseModel):
    actor: str = Field(min_length=1)
    source_keys: list[str] = Field(min_length=1)
    fps: float = Field(default=cross_camera.DEFAULT_FPS, ge=0.2, le=6.0)
    match_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    max_frames_per_source: int = Field(default=cross_camera.DEFAULT_MAX_FRAMES, ge=20, le=2000)


class SaveStillRequest(BaseModel):
    actor: str = Field(min_length=1)


@router.get("/cases/{case_id}/cross-camera/sources")
def list_sources(case_id: str) -> dict:
    if not get_case(case_id):
        raise HTTPException(404, "Case not found")
    return {"sources": cross_camera.list_sources(case_id), "models": cross_camera.models_ready()}


@router.get("/cases/{case_id}/cross-camera/runs")
def list_runs(case_id: str) -> dict:
    if not get_case(case_id):
        raise HTTPException(404, "Case not found")
    return {"runs": cross_camera.list_runs(case_id)}


@router.post("/cases/{case_id}/cross-camera/runs")
async def start_run(case_id: str, body: CorrelateRequest, background: BackgroundTasks) -> dict:
    if not get_case(case_id):
        raise HTTPException(404, "Case not found")
    if not cross_camera.models_ready()["reid"]:
        raise HTTPException(
            503,
            "Re-identification model not installed. Run "
            "`python scripts/validation/fetch_validation_assets.py` on the engine host.",
        )
    run_id = uuid.uuid4().hex
    job = await job_manager.create("cross_camera")
    persist_job(job.id, "cross_camera", "pending", result={"case_id": case_id, "run_id": run_id})

    async def _run() -> None:
        await cross_camera.run_correlation(
            run_id,
            job.id,
            case_id,
            actor=body.actor.strip(),
            source_keys=body.source_keys,
            fps=body.fps,
            match_sensitivity=body.match_sensitivity,
            max_frames_per_source=body.max_frames_per_source,
        )

    background.add_task(_run)
    return {
        "run_id": run_id,
        "job_id": job.id,
        "poll_url": f"/api/v1/jobs/{job.id}",
        "events_url": f"/api/v1/jobs/{job.id}/events",
    }


@router.get("/cross-camera/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = cross_camera.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/cross-camera/identities/{identity_id}")
def get_identity(identity_id: str) -> dict:
    ident = cross_camera.get_identity(identity_id)
    if not ident:
        raise HTTPException(404, "Identity not found")
    return ident


@router.get("/cross-camera/identities/{identity_id}/thumb")
def identity_thumb(identity_id: str) -> Response:
    path = cross_camera.identity_thumb_path(identity_id)
    if not path:
        raise HTTPException(404, "Thumbnail not found")
    return Response(path.read_bytes(), media_type="image/jpeg")


@router.get("/cross-camera/appearances/{appearance_id}/crop")
def appearance_crop(appearance_id: str, full: bool = False) -> Response:
    data = cross_camera.crop_appearance(appearance_id, full_frame=full)
    if data is None:
        raise HTTPException(404, "Could not render this appearance")
    return Response(data, media_type="image/jpeg")


@router.post("/cross-camera/runs/{run_id}/search")
async def search(
    run_id: str,
    image: UploadFile = File(...),
    mode: str = Form("appearance"),
) -> dict:
    if not cross_camera.get_run(run_id):
        raise HTTPException(404, "Run not found")
    try:
        return cross_camera.search_person(run_id, await image.read(), mode=mode)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/cross-camera/appearances/{appearance_id}/save-still")
def save_still(appearance_id: str, body: SaveStillRequest) -> dict:
    row = cross_camera._appearance_row(appearance_id)
    if not row:
        raise HTTPException(404, "Appearance not found")
    run = cross_camera.get_run(row["run_id"])
    if not run:
        raise HTTPException(404, "Run not found")
    try:
        return cross_camera.save_still_to_custody(run["case_id"], appearance_id, actor=body.actor.strip())
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
