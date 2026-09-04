from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.app import __version__
from engine.app.api.v1.acquisition import router as acquisition_router
from engine.app.api.v1.ai_analytics import router as ai_analytics_router
from engine.app.api.v1.case_transfer import router as case_transfer_router
from engine.app.api.v1.cases import router as cases_router
from engine.app.api.v1.devices import router as devices_router
from engine.app.api.v1.files import router as files_router
from engine.app.api.v1.jobs import router as jobs_router
from engine.app.api.v1.reports import router as reports_router
from engine.app.api.v1.settings import router as settings_router
from engine.app.api.v1.signing import router as signing_router
from engine.app.api.v1.tool_verification import router as verification_router
from engine.app.api.v1.live import router as live_router
from engine.app.api.v1.cross_camera import router as cross_camera_router
from engine.app.api.v1.datasets import router as datasets_router
from engine.app.api.v1.version import router as version_router
from engine.app.core.logging_setup import bootstrap

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ALLOWED_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}

_API_TOKEN = os.getenv("PRAMAAN_API_TOKEN", "").strip()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


app = FastAPI(
    title="Pramaan Engine",
    version=__version__,
    description="SIH26150 multi-vendor DVR/NVR forensic analysis engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-Pramaan-Ephemeral", "X-Pramaan-Token"],
)


@app.middleware("http")
async def enforce_local_browser_origins(request: Request, call_next):  # type: ignore[no-untyped-def]
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    if _API_TOKEN and request.url.path.startswith("/api/v1"):
        provided = request.headers.get("x-pramaan-token", "")
        if provided != _API_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    return await call_next(request)


app.include_router(version_router, prefix="/api/v1")
app.include_router(datasets_router, prefix="/api/v1")
app.include_router(cases_router, prefix="/api/v1")
app.include_router(acquisition_router, prefix="/api/v1")
app.include_router(case_transfer_router, prefix="/api/v1")
app.include_router(ai_analytics_router, prefix="/api/v1")
app.include_router(devices_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(signing_router, prefix="/api/v1")
app.include_router(verification_router, prefix="/api/v1")
app.include_router(live_router, prefix="/api/v1")
app.include_router(cross_camera_router, prefix="/api/v1")

