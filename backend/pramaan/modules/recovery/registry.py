from __future__ import annotations

from typing import Callable, TypeVar

from pramaan.recovery.base import RecoveryAdapter

T = TypeVar("T", bound=RecoveryAdapter)

_REGISTRY: dict[str, RecoveryAdapter] = {}


def register(adapter: RecoveryAdapter) -> RecoveryAdapter:
    """Register a recovery adapter by its `name` key."""
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> RecoveryAdapter | None:
    return _REGISTRY.get(name)


def all_adapters() -> dict[str, RecoveryAdapter]:
    return dict(_REGISTRY)


def bootstrap_defaults() -> None:
    if _REGISTRY:
        return
    from pramaan.recovery.adapters.dahua_dhav import DahuaDhavAdapter
    from pramaan.recovery.adapters.h264_carve import H264CarveAdapter
    from pramaan.recovery.adapters.hikvision import HikvisionAdapter

    register(DahuaDhavAdapter())
    register(HikvisionAdapter())
    register(H264CarveAdapter())
