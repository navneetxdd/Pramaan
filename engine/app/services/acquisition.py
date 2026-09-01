from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile

from engine.app.core.config import MAX_UPLOAD_BYTES
from engine.app.core.repository import (
    case_storage_dir,
    get_case,
    register_device_from_path,
)
from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.verification.honeywell_specimen import write_honeywell_specimen
from engine.app.verification.hikvision_specimen import write_hikvision_specimen
from engine.app.verification.lab_specimen import write_lab_specimen

SYNTHETIC_VENDORS = frozenset({"dahua", "honeywell", "hikvision"})

logger = logging.getLogger("forensic.engine")


async def store_upload(case_id: str, filename: str, file: UploadFile) -> Path:
    dest = case_storage_dir(case_id) / filename
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
    return dest


async def acquire_upload(case_id: str, actor: str, file: UploadFile) -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    dest = await store_upload(case_id, file.filename, file)
    identification = identify_image(dest)
    device = register_device_from_path(
        case_id,
        actor.strip(),
        dest,
        identification=identification,
    )
    _write_hash_sidecar(dest, device["image_sha256"])
    return {
        "evidence": _device_as_evidence(device),
        "identification": identification,
        "vendor_hints": identification.get("hits", []),
    }


def _write_hash_sidecar(image_path: Path, sha256_hex: str | None) -> None:
    if not sha256_hex:
        return
    sidecar = image_path.with_suffix(image_path.suffix + ".sha256")
    sidecar.write_text(f"{sha256_hex}  {image_path.name}\n", encoding="utf-8")


async def create_lab_specimen(case_id: str, actor: str, vendor: str = "dahua") -> dict:
    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    vendor_key = vendor.strip().lower()
    if vendor_key not in SYNTHETIC_VENDORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported synthetic vendor '{vendor}'. Use: {', '.join(sorted(SYNTHETIC_VENDORS))}",
        )

    if vendor_key == "honeywell":
        dest = case_storage_dir(case_id) / "lab_honeywell_specimen.bin"
        write_honeywell_specimen(dest)
    elif vendor_key == "hikvision":
        dest = case_storage_dir(case_id) / "lab_hikvision_specimen.bin"
        write_hikvision_specimen(dest)
    else:
        dest = case_storage_dir(case_id) / "lab_dahua_dhav_specimen.bin"
        write_lab_specimen(dest)

    identification = identify_image(dest)
    device = register_device_from_path(
        case_id,
        actor.strip(),
        dest,
        identification=identification,
    )
    _write_hash_sidecar(dest, device["image_sha256"])
    return {
        "evidence": _device_as_evidence(device),
        "identification": identification,
        "vendor": vendor_key,
        "specimen_type": "known_answer_fixture",
    }


def _device_as_evidence(device: dict) -> dict:
    path = Path(device["image_path"])
    import json

    identification = None
    if device.get("detection_trace_json"):
        try:
            identification = json.loads(device["detection_trace_json"])
        except json.JSONDecodeError:
            identification = None
    return {
        "id": device["id"],
        "case_id": device["case_id"],
        "filename": path.name,
        "storage_path": device["image_path"],
        "sha256": device["image_sha256"],
        "md5": device["image_md5"],
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "media_type": "disk_image",
        "acquired_at": device["acquired_at"],
        "acquisition_status": device.get("acquisition_status", "complete"),
        "verification_status": device.get("verification_status", "pending"),
        "identification": identification,
        "identification_json": device.get("detection_trace_json"),
    }
