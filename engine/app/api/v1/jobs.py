from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from engine.app.api.v1.models import JobStatus
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import get_persisted_job, persist_job
from engine.app.services.recovery import segments_as_legacy

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def _job_from_persisted(persisted: dict) -> tuple[dict, dict]:
    result: dict = {}
    if persisted.get("result_json"):
        try:
            result = json.loads(persisted["result_json"])
        except json.JSONDecodeError:
            result = {}
    device_id = result.get("device_id")
    job = {
        "id": persisted["id"],
        "case_id": result.get("case_id"),
        "image_id": device_id,
        "status": persisted["status"],
        "vendor": result.get("vendor"),
        "adapter": result.get("adapter"),
        "stats_json": persisted.get("result_json"),
        "error": persisted.get("error"),
        "started_at": persisted["created_at"],
        "completed_at": persisted["updated_at"],
        "progress": persisted.get("progress", 0),
        "message": persisted.get("message"),
    }
    return job, result


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    persisted = get_persisted_job(job_id)
    device_id = None
    result: dict = {}
    if persisted:
        job, result = _job_from_persisted(persisted)
        device_id = result.get("device_id")
    else:
        live = await job_manager.get(job_id)
        if live:
            result = live.result or {}
            device_id = result.get("device_id")
            job = {
                "id": job_id,
                "case_id": result.get("case_id"),
                "image_id": device_id,
                "status": live.status,
                "vendor": result.get("vendor"),
                "adapter": result.get("adapter"),
                "stats_json": json.dumps(result) if result else None,
                "error": live.error,
                "started_at": live.created_at,
                "completed_at": None,
                "progress": live.progress,
                "message": live.message,
            }
        else:
            raise HTTPException(status_code=404, detail="Job not found")

    segments = segments_as_legacy(device_id or job_id, result) if device_id else []
    return {
        "job": job,
        "segments": segments,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "message": job.get("message"),
    }


@router.get("/{job_id}/status", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    job = await job_manager.get(job_id)
    if job:
        return JobStatus(
            status=job.status,
            result=job.result,
            error=job.error,
            progress=job.progress,
            message=job.message,
        )

    persisted = get_persisted_job(job_id)
    if persisted:
        result = {}
        if persisted.get("result_json"):
            try:
                result = json.loads(persisted["result_json"])
            except json.JSONDecodeError:
                result = {}
        return JobStatus(
            status=persisted["status"],
            result=result or None,
            error=persisted.get("error"),
            progress=float(persisted.get("progress") or 0),
            message=persisted.get("message"),
        )

    raise HTTPException(status_code=404, detail="Job not found")


@router.post("/{job_id}/cancel", response_model=JobStatus)
async def cancel_job(job_id: str) -> JobStatus:
    job = await job_manager.cancel(job_id)
    if not job:
        persisted = get_persisted_job(job_id)
        if not persisted:
            raise HTTPException(status_code=404, detail="Job not found")
        raise HTTPException(status_code=409, detail=f"Job cannot be cancelled from status '{persisted['status']}'")
    persist_job(
        job_id,
        job.kind,
        "cancelled",
        progress=job.progress,
        message=job.message,
        error="Cancelled by operator",
    )
    return JobStatus(
        status=job.status,
        result=job.result,
        error="Cancelled by operator",
        progress=job.progress,
        message=job.message,
    )


@router.get("/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    persisted = get_persisted_job(job_id)
    live = await job_manager.get(job_id)

    if not live and persisted and persisted["status"] in _TERMINAL_STATUSES:
        async def terminal_stream():  # type: ignore[no-untyped-def]
            payload = json.dumps(
                {
                    "job_id": job_id,
                    "status": persisted["status"],
                    "progress": persisted.get("progress", 0),
                    "message": persisted.get("message"),
                    "error": persisted.get("error"),
                }
            )
            yield f"data: {payload}\n\n"

        return StreamingResponse(
            terminal_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    if not live:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():  # type: ignore[no-untyped-def]
        try:
            async for event in job_manager.subscribe(job_id):
                if event.get("heartbeat"):
                    yield ": heartbeat\n\n"
                    continue
                payload = json.dumps(event)
                yield f"data: {payload}\n\n"
                if event.get("status") in _TERMINAL_STATUSES:
                    break
        except KeyError:
            yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
