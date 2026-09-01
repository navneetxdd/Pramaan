from __future__ import annotations

import logging
import socket
from pathlib import Path

from engine.app.core.db import APP_VERSION, DATABASE_PATH, init_db
from engine.app.core.repository import reconcile_interrupted_acquisitions, reconcile_interrupted_jobs

logger = logging.getLogger("forensic.engine")


def configure_logging() -> None:
    log_dir = Path.home() / "ForensicWorkstation" / "logs"
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
    """Part B: block outbound network except localhost."""

    allowed = {"127.0.0.1", "localhost", "::1"}
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            raise OSError(f"Outbound network blocked by policy: {host}")
        return original_connect(self, address)

    def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            raise OSError(f"Outbound network blocked by policy: {host}")
        return original_create_connection(address, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.create_connection = guarded_create_connection  # type: ignore[method-assign]
    logger.info("Outbound socket guard active (localhost only)")


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
