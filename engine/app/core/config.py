from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


_DEFAULT_WORK_DIR = (
    str(ROOT / ".localdata")
    if not os.getenv("FORENSIC_WORKSTATION_DATA")
    else str(Path.home() / "ForensicWorkstation" / "data")
)
WORK_DIR = Path(_env("FORENSIC_WORKSTATION_DATA", _DEFAULT_WORK_DIR))
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
REID_MODEL_PATH = Path(_env("PRAMAAN_REID_MODEL", str(VALIDATION_DATA_DIR / "models" / "person_reid_youtu.onnx")))
SFACE_MODEL_PATH = Path(_env("PRAMAAN_SFACE_MODEL", str(VALIDATION_DATA_DIR / "models" / "face_recognition_sface.onnx")))
OEM_IMAGE_DIR = Path(_env("PRAMAAN_OEM_IMAGE_DIR", str(VALIDATION_DATA_DIR / "oem")))


def oem_drop_zone_info() -> dict[str, str | bool]:
    """Operator-facing OEM folder label — never expose another machine's absolute path."""
    env_var = "PRAMAAN_OEM_IMAGE_DIR"
    configured = os.getenv(env_var) is not None
    try:
        rel = OEM_IMAGE_DIR.resolve().relative_to(REPO_ROOT.resolve())
        label = rel.as_posix()
    except ValueError:
        label = f"${env_var}" if configured else "validation_data/oem"
    return {
        "env_var": env_var,
        "configured": configured,
        "label": label,
    }

for path in (WORK_DIR, CASES_DIR, EXPORTS_DIR, BUNDLES_DIR, REPORTS_DIR):
    path.mkdir(parents=True, exist_ok=True)
