from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_ROOT = Path(os.getenv("PRAMAAN_STORAGE_ROOT", str(BASE_DIR / "storage")))
CASES_DIR = STORAGE_ROOT / "cases"
EXPORTS_DIR = STORAGE_ROOT / "exports"
DATABASE_PATH = Path(os.getenv("PRAMAAN_DATABASE", str(BASE_DIR / "pramaan.db")))

MAX_UPLOAD_BYTES = int(os.getenv("PRAMAAN_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024 * 1024)))
FFMPEG_BIN = os.getenv("PRAMAAN_FFMPEG", "ffmpeg")

CASES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
