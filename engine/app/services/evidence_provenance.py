"""First-sector provenance stamps for fabricated / emulated media."""

from __future__ import annotations

from pathlib import Path

# UI + report copy — must not present lab images as field evidence.
LAB_SPECIMEN_BANNER = "Lab specimen — fabricated, NOT a real acquisition"

_STAMPS: tuple[tuple[bytes, str, str], ...] = (
    (b"PRAMAAN-LAB-SPECIMEN-HIKVISION", "lab_specimen", LAB_SPECIMEN_BANNER),
    (b"PRAMAAN-EMULATED-HIKVISION-FS", "emulated", "Emulated image — fabricated, NOT a real acquisition"),
    (b"CPPLUS LAB SPECIMEN", "lab_specimen", LAB_SPECIMEN_BANNER),
    (b"Honeywell HWDVR-Lab-Specimen", "lab_specimen", LAB_SPECIMEN_BANNER),
)


def detect_lab_provenance(path: Path) -> dict | None:
    """Return provenance metadata when the image carries a known lab/emulation stamp."""
    try:
        with path.open("rb") as handle:
            head = handle.read(512)
    except OSError:
        return None
    if not head:
        return None
    for stamp, kind, message in _STAMPS:
        if stamp in head:
            return {
                "kind": kind,
                "stamp": stamp.decode("latin-1", errors="replace"),
                "message": message,
                "is_lab_specimen": True,
            }
    return None
