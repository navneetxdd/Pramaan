from __future__ import annotations

import shutil

from fastapi import APIRouter

from engine.app import __version__
from engine.app.core.config import FFMPEG_BIN
from engine.app.core.signing import certificate_fingerprint
from engine.app.parsers.generic_tier2 import GenericTier2Adapter
from engine.app.parsers.registry import all_adapters

router = APIRouter(tags=["version"])


@router.get("/version")
def get_version() -> dict:
    adapters = list(all_adapters().keys())
    return {
        "status": "ok",
        "service": "pramaan-engine",
        "version": __version__,
        "signing_certificate_fingerprint": certificate_fingerprint(),
        "capabilities": {
            "ffmpeg_available": bool(shutil.which(FFMPEG_BIN)),
            "modules": [
                "device_identification",
                "acquisition",
                "case_export_import",
                "ai_analytics",
                "recovery",
                "timeline_analysis",
                "chain_of_custody",
                "reporting",
                "tool_verification",
            ],
            "recovery_adapters": adapters,
            "oem_fingerprints": [
                "Dahua",
                "Hikvision",
                "CP Plus",
                "Honeywell",
                "TP-Link",
                "Godrej",
                "Uniview",
                "Matrix",
            ],
            "hash_algorithms": ["SHA-256", "MD5"],
            "limitations": [
                "Encrypted DVR/NVR stores are not decrypted; encryption detection is not yet implemented",
                "RAID reconstruction and chip-off extraction are not supported",
                GenericTier2Adapter.degradation_message(),
                "Physical disk imaging requires elevated privileges on Windows (\\\\.\\PhysicalDriveN)",
                "E01 input requires optional pyewf — raw/DD always supported",
            ],
        },
    }
