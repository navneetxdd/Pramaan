from __future__ import annotations

import logging
import os
import socket

from engine.app.core.config import WORK_DIR
from engine.app.core.db import APP_VERSION, DATABASE_PATH, init_db
from engine.app.core.repository import reconcile_interrupted_acquisitions, reconcile_interrupted_jobs

logger = logging.getLogger("forensic.engine")


def configure_logging() -> None:
    log_dir = WORK_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "engine.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def block_outbound_sockets() -> None:
    """Block outbound network except localhost unless logical acquisition is enabled."""

    if os.getenv("PRAMAAN_ALLOW_LOGICAL_ACQUIRE", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Outbound socket guard disabled (PRAMAAN_ALLOW_LOGICAL_ACQUIRE)")
        return

    if getattr(block_outbound_sockets, "_installed", False):
        return

    allowed = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
    originals = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "create_connection": socket.create_connection,
    }
    block_outbound_sockets._originals = originals  # type: ignore[attr-defined]
    block_outbound_sockets._installed = True  # type: ignore[attr-defined]

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            raise OSError(f"Outbound network blocked by policy: {host}")
        return originals["connect"](self, address)

    def guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            return 10061
        return originals["connect_ex"](self, address)

    def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            raise OSError(f"Outbound network blocked by policy: {host}")
        return originals["create_connection"](address, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]
    socket.create_connection = guarded_create_connection  # type: ignore[method-assign]
    logger.info("Outbound socket guard active (localhost only)")


def restore_outbound_sockets() -> None:
    """Undo block_outbound_sockets — for tests that patch the guard."""
    originals = getattr(block_outbound_sockets, "_originals", None)
    if not originals:
        return
    socket.socket.connect = originals["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = originals["connect_ex"]  # type: ignore[method-assign]
    socket.create_connection = originals["create_connection"]  # type: ignore[method-assign]
    block_outbound_sockets._originals = None  # type: ignore[attr-defined]
    block_outbound_sockets._installed = False  # type: ignore[attr-defined]


def bootstrap() -> None:
    configure_logging()
    block_outbound_sockets()
    init_db()
    reconciled = reconcile_interrupted_jobs()
    if reconciled:
        logger.info("Reconciled %s interrupted job(s) from prior engine session", reconciled)
    acq_reconciled = reconcile_interrupted_acquisitions()
    if acq_reconciled:
        logger.info("Marked %s in-flight acquisition(s) interrupted after restart", acq_reconciled)
    logger.info("Engine v%s ready · db=%s", APP_VERSION, DATABASE_PATH)
