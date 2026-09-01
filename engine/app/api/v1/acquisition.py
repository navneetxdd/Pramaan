from __future__ import annotations

import json
import logging
import os
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from engine.app.core.config import oem_drop_zone_info
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import (
    get_case,
    get_device,
    list_resumable_devices,
    persist_job,
)
from engine.app.services.acquisition import acquire_oem_image, list_oem_images
from engine.app.services.disk_enumeration import list_imaging_sources
from engine.app.services.e01_reader import pyewf_available
from engine.app.services.logical_acquisition import acquire_logical_network
from engine.app.services.physical_imaging import prepare_imaging_device, run_imaging_job

logger = logging.getLogger("forensic.engine")

router = APIRouter(tags=["acquisition"])


class PhysicalAcquireRequest(BaseModel):
    actor: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_type: Literal["file", "physical", "e01"] = "file"
    write_blocker: Literal["software_read_only", "hardware", "none"] = "software_read_only"
    max_bytes: int | None = Field(default=None, ge=512)


class ResumeAcquireRequest(BaseModel):
    actor: str = Field(min_length=1)


class OemAcquireRequest(BaseModel):
    actor: str = Field(min_length=1)
    filename: str = Field(min_length=1)


class LogicalAcquireRequest(BaseModel):
    actor: str = Field(min_length=1)
    host: str = Field(min_length=1)
    port: int = Field(default=80, ge=1, le=65535)
    user: str = Field(min_length=1)
    password: str = Field(min_length=1)
    vendor: Literal["hikvision", "dahua", "onvif"] = "hikvision"
    max_clips: int = Field(default=4, ge=1, le=16)


def _source_path_from_device(device: dict) -> str:
    if device.get("bad_sector_map_json"):
        try:
            meta = json.loads(device["bad_sector_map_json"])
            if meta.get("source_path"):
                return str(meta["source_path"])
        except json.JSONDecodeError:
            pass
    raise HTTPException(status_code=400, detail="Source path missing — cannot resume this acquisition")


def _validate_source_type(source_path: str, source_type: str) -> None:
    lower = source_path.lower()
    is_e01 = lower.endswith((".e01", ".ex01"))
    is_physical = lower.startswith("\\\\.\\physicaldrive") or lower.startswith("/dev/")
    if source_type == "e01" and not is_e01:
        raise HTTPException(status_code=422, detail="E01 source type requires an .E01 or .Ex01 path")
    if source_type == "physical" and not is_physical:
        raise HTTPException(status_code=422, detail="Physical source type requires a raw device path")
    if source_type == "file" and is_physical:
        raise HTTPException(status_code=422, detail="Raw device paths must use source_type='physical'")


@router.get("/acquisition/disks")
def list_disks() -> dict:
    disks = list_imaging_sources()
    return {"disks": disks, "count": len(disks), "read_only_policy": "Sources opened rb only; writes go to case storage"}


@router.get("/acquisition/capabilities")
def acquisition_capabilities() -> dict:
    drop = oem_drop_zone_info()
    logical_enabled = os.getenv("PRAMAAN_ALLOW_LOGICAL_ACQUIRE", "").strip().lower() in {"1", "true", "yes"}
    return {
        "chunked_imaging": True,
        "checkpoint_resume": True,
        "bad_sector_zero_fill": True,
        "e01_input": pyewf_available(),
        "physical_disks": True,
        "logical_network": logical_enabled,
        "oem_drop_zone_env": drop["env_var"],
        "oem_drop_zone_label": drop["label"],
        "oem_drop_zone_configured": drop["configured"],
    }


@router.get("/acquisition/oem-images")
def oem_images() -> dict:
    images = list_oem_images()
    drop = oem_drop_zone_info()
    return {
        "env_var": drop["env_var"],
        "configured": drop["configured"],
        "label": drop["label"],
        "images": images,
        "count": len(images),
    }


@router.post("/cases/{case_id}/devices/acquire/oem")
async def acquire_oem(case_id: str, body: OemAcquireRequest) -> dict:
    try:
        return await acquire_oem_image(case_id, body.actor, body.filename)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OEM acquire failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cases/{case_id}/devices/acquire/logical")
async def acquire_logical(case_id: str, body: LogicalAcquireRequest) -> dict:
    if body.vendor == "onvif":
        raise HTTPException(
            status_code=501,
            detail="ONVIF logical acquisition is disabled — use Hikvision ISAPI or Dahua CGI",
        )
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        return await acquire_logical_network(
            case_id,
            body.actor,
            host=body.host.strip(),
            port=body.port,
            user=body.user,
            password=body.password,
            vendor=body.vendor,
            max_clips=body.max_clips,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Logical acquisition failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cases/{case_id}/acquisition/resumable")
def resumable_acquisitions(case_id: str) -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    devices = list_resumable_devices(case_id)
    return {"case_id": case_id, "devices": devices}


@router.post("/cases/{case_id}/devices/acquire/physical")
async def acquire_physical(
    case_id: str,
    body: PhysicalAcquireRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    _validate_source_type(body.source_path, body.source_type)

    try:
        device = prepare_imaging_device(
            case_id,
            body.actor,
            body.source_path,
            source_type=body.source_type,
            write_blocker=body.write_blocker,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = await job_manager.create("acquisition")
    persist_job(
        job.id,
        "acquisition",
        "pending",
        result={"case_id": case_id, "device_id": device["id"], "source_path": body.source_path},
    )

    async def _run() -> None:
        await run_imaging_job(
            job.id,
            case_id,
            device["id"],
            body.actor,
            source_path=body.source_path,
            resume=False,
            max_bytes=body.max_bytes,
        )

    background_tasks.add_task(_run)
    return {
        "job": {
            "id": job.id,
            "case_id": case_id,
            "device_id": device["id"],
            "status": "pending",
            "kind": "acquisition",
        },
        "device": device,
        "poll_url": f"/api/v1/jobs/{job.id}",
        "events_url": f"/api/v1/jobs/{job.id}/events",
    }


@router.post("/devices/{device_id}/acquire/resume")
async def resume_acquisition(
    device_id: str,
    body: ResumeAcquireRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    device = get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    case_id = device["case_id"]
    if device["acquisition_status"] not in {"interrupted", "in_progress", "pending"}:
        raise HTTPException(status_code=409, detail="Device is not resumable")

    source_path = _source_path_from_device(device)
    job = await job_manager.create("acquisition")
    persist_job(
        job.id,
        "acquisition",
        "pending",
        result={"case_id": case_id, "device_id": device_id, "source_path": source_path, "resume": True},
    )

    async def _run() -> None:
        await run_imaging_job(
            job.id,
            case_id,
            device_id,
            body.actor,
            source_path=source_path,
            resume=True,
        )

    background_tasks.add_task(_run)
    return {
        "job": {
            "id": job.id,
            "case_id": case_id,
            "device_id": device_id,
            "status": "running",
            "kind": "acquisition",
        },
        "poll_url": f"/api/v1/jobs/{job.id}",
        "events_url": f"/api/v1/jobs/{job.id}/events",
    }
