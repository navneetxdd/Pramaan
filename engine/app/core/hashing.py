from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO


def hash_stream(readable: BinaryIO, chunk_size: int = 4 * 1024 * 1024) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    while True:
        block = readable.read(chunk_size)
        if not block:
            break
        md5.update(block)
        sha256.update(block)
    return md5.hexdigest(), sha256.hexdigest()


def hash_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> tuple[str, str]:
    with path.open("rb") as handle:
        return hash_stream(handle, chunk_size)
