from __future__ import annotations

import io
from pathlib import Path


class EvidenceReader(io.RawIOBase):
    """Read-only file-like wrapper over raw images or E01 (pyewf)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None
        self._e01 = path.suffix.lower() in {".e01", ".ex01"}
        if self._e01:
            from engine.app.services.e01_reader import open_e01_readonly

            self._handle = open_e01_readonly(path)
            self._size = int(self._handle.get_media_size())
        else:
            self._file = path.open("rb")
            self._handle = self._file
            self._file.seek(0, io.SEEK_END)
            self._size = self._file.tell()

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            remaining = self._size - self.tell()
            size = remaining
        if size <= 0:
            return b""
        return self._handle.read(size)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if self._e01:
            self._handle.seek(offset)
            return int(self._handle.get_offset())
        return self._file.seek(offset, whence)

    def tell(self) -> int:
        if self._e01:
            return int(self._handle.get_offset())
        return self._file.tell()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def readable(self) -> bool:
        return True


def open_evidence_readonly(path: Path) -> EvidenceReader:
    return EvidenceReader(path)


def evidence_size(path: Path) -> int:
    lower = path.suffix.lower()
    if lower in {".e01", ".ex01"}:
        from engine.app.services.e01_reader import e01_size, open_e01_readonly

        handle = open_e01_readonly(path)
        try:
            return e01_size(handle)
        finally:
            handle.close()
    return path.stat().st_size


def read_image_bytes(image_path: Path, offset: int = 0, length: int | None = None) -> bytes:
    """Read bytes from a raw/DD image or E01 (when pyewf is installed)."""
    with open_evidence_readonly(image_path) as handle:
        handle.seek(offset)
        if length is None:
            remaining = evidence_size(image_path) - offset
            length = max(0, remaining)
        return handle.read(length)
