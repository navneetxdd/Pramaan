from __future__ import annotations

from pathlib import Path


def write_sha256_sidecar(evidence_path: Path, digest: str) -> Path:
    """Standard sidecar: `<filename>.sha256` containing hex digest."""
    sidecar = Path(f"{evidence_path}.sha256")
    sidecar.write_text(f"{digest}\n", encoding="utf-8")
    return sidecar


def read_sha256_sidecar(evidence_path: Path) -> str | None:
    sidecar = Path(f"{evidence_path}.sha256")
    if not sidecar.exists():
        return None
    return sidecar.read_text(encoding="utf-8").strip().split()[0]
