from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Support PRAMAAN_ prefix (product name) and legacy CSHIELD_ alias for team integration docs.
def _env(name: str, default: str) -> str:
    return os.getenv(f"PRAMAAN_{name}", os.getenv(f"CSHIELD_{name}", default))


BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_ROOT = Path(_env("STORAGE_ROOT", str(BASE_DIR / "storage")))
CASES_DIR = STORAGE_ROOT / "cases"
EXPORTS_DIR = STORAGE_ROOT / "exports"
DATABASE_PATH = Path(_env("DATABASE", str(BASE_DIR / "pramaan.db")))

MAX_UPLOAD_BYTES = int(_env("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024 * 1024)))
FFMPEG_BIN = _env("FFMPEG", "ffmpeg")
RECOVERY_SCAN_BYTES_DEFAULT = int(_env("RECOVERY_SCAN_BYTES", str(0)))  # 0 = full image

CASES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
