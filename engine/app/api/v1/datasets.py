from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine.app.core.config import VALIDATION_DATA_DIR
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import persist_job

router = APIRouter(prefix="/datasets", tags=["datasets"])

MANIFEST_PATH = VALIDATION_DATA_DIR / "manifest.json"
_FETCH_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "validation" / "fetch_validation_assets.py"


def _load_fetch_catalog() -> list[dict]:
    spec = importlib.util.spec_from_file_location("fetch_validation_assets", _FETCH_SCRIPT)
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalogs: list[dict] = []
    for name in (
        "DOWNLOADS",
        "SURVEILLANCE_OPTIONAL",
        "REAL_DVR_SAMPLES",
        "REAL_FS_DOWNLOADS",
        "MEVA_SAMPLE",
        "CFREDS_DOWNLOADS",
        "LARGE_OPTIONAL",
    ):
        value = getattr(module, name, None)
        if isinstance(value, list):
            catalogs.extend(value)
        elif isinstance(value, dict):
            catalogs.append(value)
    return catalogs


def _manifest_by_id() -> dict[str, dict]:
    if not MANIFEST_PATH.is_file():
        return {}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = manifest.get("assets") or []
    return {item["id"]: item for item in assets if isinstance(item, dict) and item.get("id")}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog_entry(item: dict, manifest_row: dict | None = None) -> dict:
    rel = item.get("dest") or item.get("path")
    manifest_row = manifest_row or {}
    if not rel:
        return {
            "id": item.get("id", "unknown"),
            "purpose": item.get("purpose") or manifest_row.get("purpose"),
            "present": False,
            "verified": False,
            "size_bytes": 0,
            "license": item.get("license") or manifest_row.get("license"),
            "url": item.get("url") or manifest_row.get("url"),
        }
    path = VALIDATION_DATA_DIR / rel
    present = path.is_file() and path.stat().st_size > 0
    verified = False
    size_bytes = path.stat().st_size if present else int(manifest_row.get("bytes") or item.get("bytes") or 0)
    expected = manifest_row.get("sha256") or item.get("sha256")
    if present and expected:
        verified = _sha256_file(path) == expected
    elif present and manifest_row.get("kind") == "generated_known_answer":
        verified = True
    return {
        "id": item.get("id", rel.replace("/", "_")),
        "purpose": item.get("purpose") or manifest_row.get("purpose"),
        "present": present,
        "verified": verified,
        "size_bytes": size_bytes,
        "license": item.get("license") or manifest_row.get("license"),
        "url": item.get("url") or manifest_row.get("url"),
        "path": rel,
    }


@router.get("")
def list_datasets() -> list[dict]:
    manifest_rows = _manifest_by_id()
    catalog = _load_fetch_catalog()
    seen: set[str] = set()
    rows: list[dict] = []
    for item in catalog:
        dataset_id = item.get("id")
        if not dataset_id or dataset_id in seen:
            continue
        seen.add(dataset_id)
        rows.append(_catalog_entry(item, manifest_rows.get(dataset_id)))
    for dataset_id, manifest_row in manifest_rows.items():
        if dataset_id in seen:
            continue
        rows.append(_catalog_entry(manifest_row, manifest_row))
    rows.sort(key=lambda row: row.get("id") or "")
    return rows


async def _fetch_one(dataset_id: str) -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[4]
    script = root / "scripts" / "validation" / "fetch_validation_assets.py"
    flags: list[str] = []
    if dataset_id.startswith("digitalcorpora") or "canon" in dataset_id or "cfreds" in dataset_id:
        flags.append("--real-fs")
    if dataset_id.startswith("dahua_dav") or dataset_id.startswith("hikvision") or "real_dvr" in dataset_id:
        flags.append("--real-dvr")
    if dataset_id.startswith("meva") or dataset_id.startswith("caviar"):
        flags.append("--surveillance")
    if dataset_id.startswith("digitalcorpora_ubnist1_gen3"):
        flags.append("--large")
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
