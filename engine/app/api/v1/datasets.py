from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine.app.core.config import VALIDATION_DATA_DIR
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import persist_job

router = APIRouter(prefix="/datasets", tags=["datasets"])

MANIFEST_PATH = VALIDATION_DATA_DIR / "manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog_entry(item: dict) -> dict:
    rel = item.get("path")
    if not rel:
        return {
            "id": item.get("id", "unknown"),
            "purpose": item.get("purpose"),
            "present": False,
            "verified": False,
            "size_bytes": 0,
            "license": item.get("license"),
            "url": item.get("url"),
        }
    path = VALIDATION_DATA_DIR / rel
    present = path.is_file() and path.stat().st_size > 0
    verified = False
    size_bytes = path.stat().st_size if present else int(item.get("bytes") or 0)
    expected = item.get("sha256")
    if present and expected:
        verified = _sha256_file(path) == expected
    elif present and item.get("kind") == "generated_known_answer":
        verified = True
    return {
        "id": item.get("id", rel.replace("/", "_")),
        "purpose": item.get("purpose"),
        "present": present,
        "verified": verified,
        "size_bytes": size_bytes,
        "license": item.get("license"),
        "url": item.get("url"),
        "path": rel,
    }


@router.get("")
def list_datasets() -> list[dict]:
    if not MANIFEST_PATH.is_file():
        return []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = manifest.get("assets") or []
    return [_catalog_entry(item) for item in assets if isinstance(item, dict)]


async def _fetch_one(dataset_id: str) -> None:
    import subprocess
    import sys
    from pathlib import Path as P

    root = P(__file__).resolve().parents[3]
    script = root / "scripts" / "validation" / "fetch_validation_assets.py"
    flags: list[str] = []
    if dataset_id.startswith("digitalcorpora") or "canon" in dataset_id or "cfreds" in dataset_id:
        flags.append("--real-fs")
    if dataset_id.startswith("dahua_dav") or dataset_id.startswith("hikvision") or "real_dvr" in dataset_id:
        flags.append("--real-dvr")
    if dataset_id.startswith("meva") or dataset_id.startswith("caviar"):
        flags.append("--surveillance")
    cmd = [sys.executable, str(script), *flags]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "fetch failed")


@router.post("/{dataset_id}/fetch")
async def fetch_dataset(dataset_id: str, background_tasks: BackgroundTasks) -> dict:
    job = await job_manager.create("dataset_fetch")
    persist_job(job.id, "dataset_fetch", "pending", result={"dataset_id": dataset_id})

    async def _run() -> None:
        await job_manager.update(job.id, status="running", progress=10, message=f"Fetching {dataset_id}")
        try:
            await _fetch_one(dataset_id)
            await job_manager.update(job.id, status="completed", progress=100, message="Fetch complete")
            persist_job(job.id, "dataset_fetch", "completed", progress=100, message="Fetch complete")
        except Exception as exc:
            await job_manager.update(job.id, status="failed", error=str(exc))
            persist_job(job.id, "dataset_fetch", "failed", error=str(exc))

    background_tasks.add_task(_run)
    return {"job_id": job.id, "dataset_id": dataset_id, "status": "pending"}
