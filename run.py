#!/usr/bin/env python3
"""Launch Pramaan engine (backend-only dev mode for API testing — not the application)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.chdir(ROOT)

if not os.environ.get("FORENSIC_WORKSTATION_DATA"):
    os.environ["FORENSIC_WORKSTATION_DATA"] = str(ROOT / ".localdata")

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("FORENSIC_ENGINE_PORT", "8787"))
    reload = os.environ.get("FORENSIC_ENGINE_DEV", "").strip() == "1"
    uvicorn.run("engine.app.main:app", host="127.0.0.1", port=port, reload=reload)
