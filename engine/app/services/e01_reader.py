from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("forensic.engine")

_pyewf = None
_checked = False


def pyewf_available() -> bool:
    global _pyewf, _checked
    if _checked:
        return _pyewf is not None
    _checked = True
    try:
        import pyewf  # type: ignore

        _pyewf = pyewf
    except ImportError:
        _pyewf = None
        logger.info("pyewf not installed — E01 input requires raw/DD upload or pyewf")
    return _pyewf is not None


def open_e01_readonly(path: Path):
    if not pyewf_available():
        raise RuntimeError("E01 support requires pyewf — install pyewf or provide raw/DD image")
    assert _pyewf is not None
    filenames = _pyewf.glob(str(path))
    handle = _pyewf.handle()
    handle.open(filenames)
    return handle


def e01_size(handle) -> int:
    return int(handle.get_media_size())


def read_e01(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    return handle.read(size)
