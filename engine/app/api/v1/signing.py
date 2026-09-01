from __future__ import annotations

from fastapi import APIRouter

from engine.app.core.signing import certificate_fingerprint, list_signing_history

router = APIRouter(prefix="/signing", tags=["signing"])


@router.get("/history")
def signing_history() -> dict:
    return {
        "active_fingerprint": certificate_fingerprint(),
        "entries": list_signing_history(),
    }
