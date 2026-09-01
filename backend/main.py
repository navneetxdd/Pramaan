from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pramaan import __version__
from pramaan.api.router import router as core_router
from pramaan.config import EXPORTS_DIR
from pramaan.core.database import init_db
from pramaan.modules.analysis.router import router as analysis_router
from pramaan.modules.recovery.registry import bootstrap_defaults
from pramaan.modules.reporting.router import router as reporting_router

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(
    title="Pramaan",
    version=__version__,
    description="Multi-vendor DVR/NVR forensic analysis",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core_router)
app.include_router(analysis_router)
app.include_router(reporting_router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    bootstrap_defaults()


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
