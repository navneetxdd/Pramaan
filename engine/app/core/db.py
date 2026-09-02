from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from engine.app.core.config import APP_VERSION, WORK_DIR

DATABASE_PATH = WORK_DIR / "forensic.db"
SCHEMA_VERSION = 8

_LOCK = threading.Lock()

PART_F_DDL = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  examiner_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  notes TEXT,
  ephemeral INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  declared_brand TEXT,
  detected_engine TEXT,
  detection_confidence REAL,
  detection_trace_json TEXT,
  model_hint TEXT,
  serial_hint TEXT,
  image_path TEXT NOT NULL,
  image_md5 TEXT,
  image_sha256 TEXT,
  acquisition_status TEXT NOT NULL DEFAULT 'in_progress',
  bad_sector_map_json TEXT,
  acquired_at TEXT,
  drift_offset_seconds REAL DEFAULT 0,
  source_type TEXT,
  source_identifier TEXT,
  source_size_bytes INTEGER,
  acquisition_started_at TEXT,
  acquisition_completed_at TEXT,
  acquisition_tool_version TEXT,
  acquisition_method TEXT,
  acquisition_operator TEXT,
  write_blocker TEXT,
  acquisition_error TEXT,
  verification_status TEXT NOT NULL DEFAULT 'pending',
  verification_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS acquisition_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  bytes_written INTEGER NOT NULL,
  running_md5_state BLOB NOT NULL,
  checkpoint_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recovered_sequences (
  id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  channel INTEGER NOT NULL,
  start_ts_raw TEXT,
  end_ts_raw TEXT,
  start_ts_corrected TEXT,
  end_ts_corrected TEXT,
  confidence TEXT NOT NULL,
  validation_level TEXT NOT NULL,
  output_path TEXT NOT NULL,
  output_md5 TEXT NOT NULL,
  output_sha256 TEXT NOT NULL,
  frame_count INTEGER NOT NULL,
  byte_start INTEGER,
  byte_end INTEGER,
  byte_length INTEGER,
  codec TEXT,
  recorder_start_ts TEXT,
  recorder_end_ts TEXT,
  corrected_start_ts TEXT,
  corrected_end_ts TEXT,
  offset_order INTEGER,
  timestamp_source TEXT,
  timestamp_confidence REAL,
  parser_name TEXT,
  parser_version TEXT,
  recovery_job_id TEXT,
  signature_evidence_json TEXT,
  validation_evidence_json TEXT,
  playable_frame_count INTEGER
);

CREATE TABLE IF NOT EXISTS custody_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp_utc TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  prev_row_hash TEXT NOT NULL,
  this_row_hash TEXT NOT NULL,
  evidence_digest TEXT
);

CREATE TABLE IF NOT EXISTS ai_findings (
  id TEXT PRIMARY KEY,
  sequence_id TEXT NOT NULL REFERENCES recovered_sequences(id) ON DELETE CASCADE,
  frame_offset_ms INTEGER NOT NULL,
  finding_type TEXT NOT NULL,
  label TEXT,
  confidence REAL,
  bbox_json TEXT,
  report_state TEXT NOT NULL DEFAULT 'EXCLUDED'
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  generated_at TEXT NOT NULL,
  output_path TEXT NOT NULL,
  output_sha256 TEXT NOT NULL,
  pades_certificate_fingerprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_verification_runs (
  id TEXT PRIMARY KEY,
  run_at TEXT NOT NULL,
  app_version TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  results_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  case_id TEXT,
  device_id TEXT,
  status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  message TEXT,
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_devices (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  host TEXT NOT NULL,
  port INTEGER NOT NULL,
  scheme TEXT NOT NULL DEFAULT 'http',
  vendor TEXT NOT NULL,
  channel_count INTEGER NOT NULL DEFAULT 1,
  model_hint TEXT,
  serial_hint TEXT,
  firmware_hint TEXT,
  channels_json TEXT NOT NULL,
  added_by TEXT NOT NULL,
  added_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_devices_case ON devices(case_id);
CREATE INDEX IF NOT EXISTS idx_custody_target ON custody_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_sequences_device ON recovered_sequences(device_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(PART_F_DDL)
        _apply_migrations(conn)


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = _column_names(conn, table)
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _apply_migrations(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current < 2:
        _add_columns(
            conn,
            "devices",
            {
                "source_type": "TEXT",
                "source_identifier": "TEXT",
                "source_size_bytes": "INTEGER",
                "acquisition_started_at": "TEXT",
                "acquisition_completed_at": "TEXT",
                "acquisition_tool_version": "TEXT",
                "acquisition_method": "TEXT",
                "write_blocker": "TEXT",
                "verification_status": "TEXT NOT NULL DEFAULT 'pending'",
                "verification_checked_at": "TEXT",
            },
        )
        _add_columns(conn, "jobs", {"case_id": "TEXT", "device_id": "TEXT"})
    if current < 3:
        _add_columns(
            conn,
            "devices",
            {
                "acquisition_operator": "TEXT",
                "acquisition_error": "TEXT",
            },
        )
    if current < 4:
        _add_columns(
            conn,
            "recovered_sequences",
            {
                "byte_start": "INTEGER",
                "byte_end": "INTEGER",
                "byte_length": "INTEGER",
                "codec": "TEXT",
                "recorder_start_ts": "TEXT",
                "recorder_end_ts": "TEXT",
                "corrected_start_ts": "TEXT",
                "corrected_end_ts": "TEXT",
                "offset_order": "INTEGER",
                "timestamp_source": "TEXT",
                "timestamp_confidence": "REAL",
                "parser_name": "TEXT",
                "parser_version": "TEXT",
                "signature_evidence_json": "TEXT",
                "validation_evidence_json": "TEXT",
            },
        )
    if current < 5:
        _add_columns(conn, "recovered_sequences", {"recovery_job_id": "TEXT"})
    if current < 6:
        _add_columns(conn, "custody_log", {"evidence_digest": "TEXT"})
    if current < 7:
        _add_columns(conn, "cases", {"ephemeral": "INTEGER NOT NULL DEFAULT 0"})
    if current < 8:
        _add_columns(conn, "ai_findings", {"report_state": "TEXT NOT NULL DEFAULT 'EXCLUDED'"})
        _add_columns(conn, "recovered_sequences", {"playable_frame_count": "INTEGER"})
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS live_devices (
              id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
              display_name TEXT NOT NULL,
              host TEXT NOT NULL,
              port INTEGER NOT NULL,
              scheme TEXT NOT NULL DEFAULT 'http',
              vendor TEXT NOT NULL,
              channel_count INTEGER NOT NULL DEFAULT 1,
              model_hint TEXT,
              serial_hint TEXT,
              firmware_hint TEXT,
              channels_json TEXT NOT NULL,
              added_by TEXT NOT NULL,
              added_at TEXT NOT NULL
            );
            """
        )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def compute_custody_hash(
    prev_hash: str,
    timestamp_utc: str,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    evidence_digest: str | None = None,
) -> str:
    payload = f"{prev_hash}|{timestamp_utc}|{actor}|{action}|{target_type}|{target_id}"
    if evidence_digest:
        payload = f"{payload}|{evidence_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_custody(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    evidence_digest: str | None = None,
) -> None:
    ts = utc_now()
    last = conn.execute(
        "SELECT this_row_hash FROM custody_log WHERE target_type = ? AND target_id = ? ORDER BY id DESC LIMIT 1",
        (target_type, target_id),
    ).fetchone()
    prev = last["this_row_hash"] if last else "GENESIS"
    this_hash = compute_custody_hash(
        prev, ts, actor, action, target_type, target_id, evidence_digest=evidence_digest
    )
    conn.execute(
        """
        INSERT INTO custody_log (
          timestamp_utc, actor, action, target_type, target_id,
          prev_row_hash, this_row_hash, evidence_digest
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, actor, action, target_type, target_id, prev, this_hash, evidence_digest),
    )


def verify_custody_chain(target_type: str, target_id: str) -> dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp_utc, actor, action, target_type, target_id,
                   prev_row_hash, this_row_hash, evidence_digest
            FROM custody_log
            WHERE target_type = ? AND target_id = ?
            ORDER BY id ASC
            """,
            (target_type, target_id),
        ).fetchall()

    if not rows:
        return {"intact": True, "first_broken_row_id": None, "tip_hash": None}

    expected_prev = "GENESIS"
    tip_hash: str | None = None
    for row in rows:
        if row["prev_row_hash"] != expected_prev:
            return {"intact": False, "first_broken_row_id": row["id"]}
        digest = row["evidence_digest"] if "evidence_digest" in row.keys() else None
        recomputed = compute_custody_hash(
            row["prev_row_hash"],
            row["timestamp_utc"],
            row["actor"],
            row["action"],
            row["target_type"],
            row["target_id"],
            evidence_digest=digest,
        )
        if recomputed != row["this_row_hash"]:
            return {"intact": False, "first_broken_row_id": row["id"]}
        expected_prev = row["this_row_hash"]
        tip_hash = row["this_row_hash"]

    return {"intact": True, "first_broken_row_id": None, "tip_hash": tip_hash}
