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
# Staging folder the operator drops seized media into. Defaults to a folder
# inside the workstation's own data directory (empty on a fresh install), not
# the repository's test-fixture directory.
INCOMING_DIR = WORK_DIR / "incoming"
OEM_IMAGE_DIR = Path(_env("PRAMAAN_OEM_IMAGE_DIR", str(INCOMING_DIR)))


def oem_drop_zone_info() -> dict[str, str | bool]:
    """Operator-facing label for the drop folder. Never exposes an absolute path
    or an environment-variable name to the UI."""
    configured = os.getenv("PRAMAAN_OEM_IMAGE_DIR") is not None
    if not configured:
        label = "the workstation's incoming media folder"
    else:
        try:
            label = OEM_IMAGE_DIR.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            label = "the configured media folder"
    return {"env_var": "PRAMAAN_OEM_IMAGE_DIR", "configured": configured, "label": label}


for path in (WORK_DIR, CASES_DIR, EXPORTS_DIR, BUNDLES_DIR, REPORTS_DIR, INCOMING_DIR):
    path.mkdir(parents=True, exist_ok=True)
