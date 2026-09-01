from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile

from pramaan.config import CASES_DIR, MAX_UPLOAD_BYTES
from pramaan.core import cases as case_store
from pramaan.core.database import sha256_file
from pramaan.modules.acquisition.sidecar import write_sha256_sidecar
from pramaan.recovery.adapters.dahua_dhav import detect_vendors

logger = logging.getLogger(__name__)


async def acquire_disk_image(case_id: str, actor: str, file: UploadFile) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    dest = case_dir / file.filename

    size = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Upload exceeds configured limit")
            handle.write(chunk)

    digest = sha256_file(dest)
    write_sha256_sidecar(dest, digest)

    existing = case_store.list_evidence(case_id)
    if any(item["sha256"] == digest for item in existing):
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Evidence with identical SHA-256 already registered for this case")

    evidence = case_store.register_evidence(case_id, file.filename, dest, actor.strip())
    vendors = detect_vendors(dest)
    logger.info("Acquired %s (%s bytes) case=%s", file.filename, size, case_id)
    return {
        "evidence": evidence,
        "vendor_hints": [hit.__dict__ for hit in vendors],
        "sidecar": f"{dest}.sha256",
    }
