from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.app.core.config import WORK_DIR
from engine.app.core.signing import certificate_fingerprint, signing_storage_backend

router = APIRouter(prefix="/settings", tags=["settings"])


class AppSettings(BaseModel):
    working_directory: str
    signing_certificate_fingerprint: str
    signing_key_storage: str
    signature_trust: str
    working_directory_configuration: str


class AppSettingsUpdate(BaseModel):
    working_directory: str = Field(min_length=1, max_length=500)


@router.get("", response_model=AppSettings)
def get_settings() -> AppSettings:
    return AppSettings(
        working_directory=str(WORK_DIR),
        signing_certificate_fingerprint=certificate_fingerprint(),
        signing_key_storage=signing_storage_backend(),
        signature_trust="self_signed_integrity",
        working_directory_configuration="FORENSIC_WORKSTATION_DATA at engine startup",
    )


@router.put("", response_model=AppSettings)
def update_settings(body: AppSettingsUpdate) -> AppSettings:
    requested = Path(body.working_directory.strip()).expanduser().resolve()
    if requested != WORK_DIR.resolve():
        raise HTTPException(
            status_code=409,
            detail="Runtime relocation is unsupported. Set FORENSIC_WORKSTATION_DATA before starting the engine.",
        )
    return get_settings()
