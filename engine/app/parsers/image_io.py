from __future__ import annotations

from pathlib import Path


def read_image_bytes(image_path: Path, offset: int = 0, length: int | None = None) -> bytes:
    """Read bytes from a raw/DD image or E01 (when pyewf is installed)."""
    lower = image_path.suffix.lower()
    if lower in {".e01", ".ex01"}:
        from engine.app.services.e01_reader import open_e01_readonly, read_e01

        handle = open_e01_readonly(image_path)
        try:
            if length is None:
                length = max(0, int(handle.get_media_size()) - offset)
            return read_e01(handle, offset, length)
        finally:
            handle.close()
    with image_path.open("rb") as handle:
        handle.seek(offset)
        return handle.read(length if length is not None else -1)


def image_size_bytes(image_path: Path) -> int:
    lower = image_path.suffix.lower()
    if lower in {".e01", ".ex01"}:
        from engine.app.services.e01_reader import e01_size, open_e01_readonly

        handle = open_e01_readonly(image_path)
        try:
            return e01_size(handle)
        finally:
            handle.close()
    return image_path.stat().st_size
