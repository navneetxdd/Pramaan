from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


WORK_DIR = Path(_env("FORENSIC_WORKSTATION_DATA", str(Path.home() / "ForensicWorkstation" / "data")))
CASES_DIR = WORK_DIR / "cases"
EXPORTS_DIR = WORK_DIR / "exports"
BUNDLES_DIR = WORK_DIR / "bundles"
REPORTS_DIR = WORK_DIR / "reports"
MAX_UPLOAD_BYTES = int(_env("FORENSIC_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024 * 1024)))
CHUNK_SIZE = int(_env("FORENSIC_CHUNK_SIZE", str(4 * 1024 * 1024)))
CHECKPOINT_INTERVAL = int(_env("FORENSIC_CHECKPOINT_MB", "512")) * 1024 * 1024
FFMPEG_BIN = _env("FORENSIC_FFMPEG", "ffmpeg")
APP_VERSION = "0.6.0"
REPO_ROOT = ROOT
VALIDATION_DATA_DIR = REPO_ROOT / "validation_data"
YUNET_MODEL_PATH = Path(_env("PRAMAAN_YUNET_MODEL", str(VALIDATION_DATA_DIR / "models" / "face_detection_yunet_2023mar.onnx")))
YOLOX_MODEL_PATH = Path(_env("PRAMAAN_YOLOX_MODEL", str(VALIDATION_DATA_DIR / "models" / "yolox_nano.onnx")))
OEM_IMAGE_DIR = Path(_env("PRAMAAN_OEM_IMAGE_DIR", str(VALIDATION_DATA_DIR / "oem")))

for path in (WORK_DIR, CASES_DIR, EXPORTS_DIR, BUNDLES_DIR, REPORTS_DIR):
    path.mkdir(parents=True, exist_ok=True)
