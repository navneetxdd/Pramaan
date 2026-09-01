from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from engine.app.core.job_manager import job_manager
from engine.app.core.repository import get_case, get_device, list_ai_findings_for_device, persist_job
from engine.app.services.ai_analytics import run_ai_analytics_job

router = APIRouter(tags=["ai-analytics"])


class AiAnalyticsRequest(BaseModel):
    actor: str = Field(min_length=1)


@router.post("/devices/{device_id}/ai-analytics")
async def start_ai_analytics(
    device_id: str,
    body: AiAnalyticsRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    case_id = device["case_id"]
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")

    job = await job_manager.create("ai_analytics")
    persist_job(
        job.id,
        "ai_analytics",
        "pending",
        result={"case_id": case_id, "device_id": device_id},
    )

    async def _run() -> None:
        await run_ai_analytics_job(job.id, case_id, device_id, body.actor)

    background_tasks.add_task(_run)
    return {
        "job": {"id": job.id, "status": "running", "kind": "ai_analytics"},
        "poll_url": f"/api/v1/jobs/{job.id}",
        "events_url": f"/api/v1/jobs/{job.id}/events",
    }


@router.get("/devices/{device_id}/ai-findings")
def list_device_ai_findings(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    findings = list_ai_findings_for_device(device_id)
    return {"device_id": device_id, "findings": findings, "count": len(findings)}
