from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("forensic.engine")


@dataclass(frozen=True)
class DiskCandidate:
    id: str
    path: str
    label: str
    size_bytes: int
    bus_type: str
    read_only_capable: bool


def list_imaging_sources() -> list[dict]:
    """Enumerate attachable imaging sources (physical/logical volumes)."""
    if platform.system() == "Windows":
        return _list_windows_sources()
    return _list_unix_sources()


def _list_windows_sources() -> list[dict]:
    script = (
        "Get-Disk | Where-Object { $_.BusType -ne 'File Backed Virtual' } | "
        "Select-Object Number,FriendlyName,Size,BusType,OperationalStatus | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        payload = json.loads(proc.stdout)
        rows = payload if isinstance(payload, list) else [payload]
        out: list[dict] = []
        for row in rows:
            number = row.get("Number")
            if number is None:
                continue
            size = int(row.get("Size") or 0)
            label = str(row.get("FriendlyName") or f"PhysicalDrive{number}")
            bus = str(row.get("BusType") or "Unknown")
            out.append(
                {
                    "id": f"physicaldrive{number}",
                    "path": fr"\\.\PhysicalDrive{number}",
                    "label": label,
                    "size_bytes": size,
                    "bus_type": bus,
                    "read_only_capable": True,
                    "requires_admin": True,
                }
            )
        return out
    except Exception:
        logger.exception("Windows disk enumeration failed")
        return []


def _list_unix_sources() -> list[dict]:
    try:
        proc = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL"], capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return []
        payload = json.loads(proc.stdout)
        out: list[dict] = []
        for dev in payload.get("blockdevices", []):
            if dev.get("type") not in {"disk", "part"}:
                continue
            name = dev.get("name")
            if not name:
                continue
            out.append(
                {
                    "id": name,
                    "path": f"/dev/{name}",
                    "label": str(dev.get("model") or name),
                    "size_bytes": int(dev.get("size") or 0),
                    "bus_type": str(dev.get("type") or "block"),
                    "read_only_capable": True,
                    "requires_admin": True,
                }
            )
        return out
    except Exception:
        logger.exception("Unix disk enumeration failed")
        return []


def open_source_readonly(source_path: str):
    """Open an imaging source read-only. Never write to the source path."""
    path = source_path.strip()
    if path.startswith("\\\\.\\") or path.startswith("/dev/"):
        return open(path, "rb", buffering=0)
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Source not found: {path}")
    return file_path.open("rb")


def source_size_bytes(source_path: str) -> int | None:
    path = source_path.strip()
    if path.startswith("\\\\.\\") or path.startswith("/dev/"):
        return None
    return Path(path).stat().st_size

