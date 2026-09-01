from __future__ import annotations

from engine.app.parsers.base import RecoveryAdapter
from engine.app.parsers.dahua_dhfs import DahuaDhavAdapter
from engine.app.parsers.generic_fallback import H264CarveAdapter
from engine.app.parsers.generic_tier2 import GenericTier2Adapter
from engine.app.parsers.hikvision import HikvisionAdapter
from engine.app.parsers.honeywell import HoneywellAdapter

_REGISTRY: dict[str, RecoveryAdapter] = {}


def register(adapter: RecoveryAdapter) -> RecoveryAdapter:
    _REGISTRY[adapter.name] = adapter
    return adapter


def get(name: str) -> RecoveryAdapter | None:
    return _REGISTRY.get(name)


def bootstrap_defaults() -> None:
    if _REGISTRY:
        return
    register(DahuaDhavAdapter())
    register(HikvisionAdapter())
    register(H264CarveAdapter())
    register(GenericTier2Adapter())
    register(HoneywellAdapter())


def all_adapters() -> dict[str, RecoveryAdapter]:
    bootstrap_defaults()
    return dict(_REGISTRY)
