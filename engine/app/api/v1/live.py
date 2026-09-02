from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from engine.app.services import live_devices

router = APIRouter(tags=["live"])


class LiveDeviceCreate(BaseModel):
    actor: str
    display_name: str
    host: str
    port: int = 554
    scheme: str = "http"
    vendor: str
    user: str = ""
    password: str = ""
    rtsp_url_override: str | None = None


class LiveReconnect(BaseModel):
    user: str
    password: str


class LiveActor(BaseModel):
    actor: str


class LiveSnapshot(BaseModel):
    actor: str
    channel: int = 1


class LiveCapture(BaseModel):
    actor: str
    channel: int = 1
    duration_s: int = Field(default=30, ge=1, le=120)


def _gate() -> None:
    if not live_devices._gate_enabled():
        raise HTTPException(
            status_code=403,
            detail="Live device access requires PRAMAAN_ALLOW_LOGICAL_ACQUIRE=1",
        )


@router.post("/cases/{case_id}/live-devices")
def create_live_device(case_id: str, body: LiveDeviceCreate) -> dict:
    _gate()
    try:
        return live_devices.add_live_device(
            case_id,
            actor=body.actor.strip(),
            display_name=body.display_name.strip(),
            host=body.host.strip(),
            port=body.port,
            scheme=body.scheme,  # type: ignore[arg-type]
            vendor=body.vendor,  # type: ignore[arg-type]
            user=body.user,
            password=body.password,
            rtsp_url_override=body.rtsp_url_override,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/cases/{case_id}/live-devices")
def list_case_live_devices(case_id: str) -> dict:
    _gate()
    return {"devices": live_devices.list_live_devices(case_id)}


@router.post("/live-devices/{device_id}/reconnect")
def reconnect_live_device(device_id: str, body: LiveReconnect) -> dict:
    _gate()
    try:
        return live_devices.reconnect_live_device(device_id, user=body.user, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/live-devices/{device_id}")
def remove_live_device(device_id: str, body: LiveActor) -> dict:
    _gate()
    try:
        live_devices.delete_live_device(device_id, actor=body.actor.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"removed": True, "id": device_id}


@router.get("/live-devices/{device_id}/stream.mjpeg")
async def stream_mjpeg(
    device_id: str,
    request: Request,
    channel: int = Query(1, ge=1),
    fps: int = Query(6, ge=1, le=15),
) -> StreamingResponse:
    _gate()
    if not live_devices.get_live_device(device_id):
        raise HTTPException(status_code=404, detail="Live device not found")
    try:
        generator = live_devices.iter_mjpeg(device_id, channel, fps, request.is_disconnected)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(generator, media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/live-devices/{device_id}/stream.mp4")
async def stream_mp4(
    device_id: str,
    request: Request,
    channel: int = Query(1, ge=1),
    quality: str = Query("main"),
) -> StreamingResponse:
    _gate()
    if not live_devices.get_live_device(device_id):
        raise HTTPException(status_code=404, detail="Live device not found")
    try:
        generator = live_devices.iter_mp4(device_id, channel, request.is_disconnected)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(generator, media_type="video/mp4")


@router.post("/live-devices/{device_id}/snapshot")
def live_snapshot(device_id: str, body: LiveSnapshot) -> dict:
    _gate()
    row = live_devices.get_live_device(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Live device not found")
    try:
        return live_devices.capture_snapshot(
            row["case_id"],
            device_id,
            actor=body.actor.strip(),
            channel=body.channel,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/live-devices/{device_id}/capture")
def live_capture(device_id: str, body: LiveCapture) -> dict:
    _gate()
    row = live_devices.get_live_device(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Live device not found")
    try:
        return live_devices.capture_clip(
            row["case_id"],
            device_id,
            actor=body.actor.strip(),
            channel=body.channel,
            duration_s=body.duration_s,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
