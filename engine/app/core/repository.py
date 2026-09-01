from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from engine.app.core.config import APP_VERSION, CASES_DIR
from engine.app.core.db import append_custody, get_db, utc_now, verify_custody_chain
from engine.app.core.hashing import hash_file


def create_case(name: str, examiner_name: str, notes: str | None = None, *, ephemeral: bool = False) -> dict:
    case_id = uuid.uuid4().hex
    created_at = utc_now()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO cases (id, name, examiner_name, created_at, notes, ephemeral) VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, name.strip(), examiner_name.strip(), created_at, notes, 1 if ephemeral else 0),
        )
        append_custody(
            conn,
            actor=examiner_name.strip(),
            action="case_created",
            target_type="case",
            target_id=case_id,
        )
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row)


def get_case(case_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def list_cases() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_case(case_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM jobs WHERE case_id = ?", (case_id,))
        conn.execute(
            "DELETE FROM custody_log WHERE target_type = 'case' AND target_id = ?",
            (case_id,),
        )
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    case_dir = (CASES_DIR / case_id).resolve()
    cases_root = CASES_DIR.resolve()
    if case_dir.parent == cases_root and case_dir.exists():
        shutil.rmtree(case_dir)
    return True


def delete_ephemeral_cases() -> int:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM cases WHERE ephemeral = 1").fetchall()
    removed = 0
    for row in rows:
        if delete_case(str(row["id"])):
            removed += 1
    return removed


def delete_cases_matching(patterns: list[Any]) -> int:
    removed = 0
    for case in list_cases():
        name = str(case.get("name") or "")
        if any(pattern.search(name) for pattern in patterns):
            if delete_case(case["id"]):
                removed += 1
    return removed


def get_device(device_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def list_devices(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM devices WHERE case_id = ? ORDER BY acquired_at DESC NULLS LAST",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def register_pending_device(
    case_id: str,
    image_path: Path,
    *,
    acquisition_status: str = "pending",
    metadata: dict | None = None,
) -> dict:
    """Register a device row before chunked imaging completes (no hashes yet)."""
    device_id = uuid.uuid4().hex
    now = utc_now()
    metadata = metadata or {}
    meta_json = json.dumps(metadata) if metadata else None
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO devices (
              id, case_id, declared_brand, detected_engine, detection_confidence,
              detection_trace_json, image_path, image_md5, image_sha256,
              acquisition_status, bad_sector_map_json, acquired_at, source_type,
              source_identifier, source_size_bytes, acquisition_started_at,
              acquisition_tool_version, acquisition_method, acquisition_operator,
              write_blocker, acquisition_error, verification_status
            ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending')
            """,
            (
                device_id,
                case_id,
                str(image_path),
                acquisition_status,
                meta_json,
                now,
                metadata.get("source_type"),
                metadata.get("source_identifier") or metadata.get("source_path"),
                metadata.get("source_size_bytes"),
                now,
                APP_VERSION,
                metadata.get("acquisition_method", "block_copy"),
                metadata.get("acquisition_operator"),
                metadata.get("write_blocker", "software_read_only"),
            ),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row)


def register_device_from_path(
    case_id: str,
    actor: str,
    image_path: Path,
    *,
    media_label: str | None = None,
    identification: dict | None = None,
    acquisition_status: str = "complete",
    acquisition_method: str = "logical_file_acquisition",
    write_blocker: str = "source_opened_read_only",
    source_type: str = "file",
    source_identifier: str | None = None,
) -> dict:
    device_id = uuid.uuid4().hex
    md5, sha256 = hash_file(image_path)
    now = utc_now()
    trace = json.dumps(identification) if identification else None
    detected = None
    confidence = None
    if identification and identification.get("hits"):
        top = identification["hits"][0]
        detected = top.get("adapter") or top.get("vendor")
        confidence = top.get("confidence")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO devices (
              id, case_id, declared_brand, detected_engine, detection_confidence,
              detection_trace_json, image_path, image_md5, image_sha256,
              acquisition_status, acquired_at, source_type, source_identifier,
              source_size_bytes, acquisition_started_at, acquisition_completed_at,
              acquisition_tool_version, acquisition_method, write_blocker,
              acquisition_operator, acquisition_error, verification_status, verification_checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                case_id,
                identification["hits"][0]["vendor"] if identification and identification.get("hits") else None,
                detected,
                confidence,
                trace,
                str(image_path),
                md5,
                sha256,
                acquisition_status,
                now,
                source_type,
                source_identifier or str(image_path),
                image_path.stat().st_size,
                now,
                now,
                APP_VERSION,
                acquisition_method,
                write_blocker,
                actor,
                None,
                "verified",
                now,
            ),
        )
        append_custody(
            conn,
            actor=actor,
            action="evidence_acquired",
            target_type="case",
            target_id=case_id,
            evidence_digest=f"sha256:{sha256}",
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row)


def update_device_identification(device_id: str, identification: dict) -> None:
    hits = identification.get("hits") or []
    with get_db() as conn:
        conn.execute(
            """
            UPDATE devices SET detection_trace_json = ?, detected_engine = ?, detection_confidence = ?,
              declared_brand = ?
            WHERE id = ?
            """,
            (
                json.dumps(identification),
                hits[0]["adapter"] if hits else None,
                hits[0]["confidence"] if hits else None,
                hits[0]["vendor"] if hits else None,
                device_id,
            ),
        )


def verify_device_integrity(device_id: str) -> dict:
    device = get_device(device_id)
    if not device:
        raise ValueError("Device not found")
    path = Path(device["image_path"])
    if not path.exists():
        update_device_verification(device_id, "missing")
        return {"ok": False, "reason": "file_missing", "expected_sha256": device["image_sha256"]}
    if not device["image_sha256"]:
        update_device_verification(device_id, "pending")
        return {"ok": False, "reason": "hash_pending", "expected_sha256": None}
    md5, sha256 = hash_file(path)
    sha_ok = sha256 == device["image_sha256"]
    md5_ok = device["image_md5"] is None or md5 == device["image_md5"]
    update_device_verification(device_id, "verified" if sha_ok and md5_ok else "mismatch")
    return {
        "ok": sha_ok and md5_ok,
        "expected_sha256": device["image_sha256"],
        "actual_sha256": sha256,
        "expected_md5": device["image_md5"],
        "actual_md5": md5,
        "sha256_ok": sha_ok,
        "md5_ok": md5_ok,
    }


def update_device_verification(device_id: str, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE devices SET verification_status = ?, verification_checked_at = ? WHERE id = ?",
            (status, utc_now(), device_id),
        )


def persist_job(job_id: str, kind: str, status: str, **fields: Any) -> None:
    now = utc_now()
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        result = fields.get("result") if "result" in fields else None
        result_json = json.dumps(result) if result is not None else (existing["result_json"] if existing else None)
        case_id = fields.get("case_id") or (result.get("case_id") if isinstance(result, dict) else None)
        device_id = fields.get("device_id") or (result.get("device_id") if isinstance(result, dict) else None)
        if existing:
            conn.execute(
                """
                UPDATE jobs SET status = ?, case_id = ?, device_id = ?, progress = ?,
                  message = ?, result_json = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    case_id or existing["case_id"],
                    device_id or existing["device_id"],
                    fields.get("progress", existing["progress"]),
                    fields.get("message", existing["message"]),
                    result_json,
                    fields.get("error", existing["error"]),
                    now,
                    job_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs (
                  id, kind, case_id, device_id, status, progress, message,
                  result_json, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    case_id,
                    device_id,
                    status,
                    fields.get("progress", 0),
                    fields.get("message"),
                    result_json,
                    fields.get("error"),
                    now,
                    now,
                ),
            )


def get_persisted_job(job_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def reconcile_interrupted_jobs() -> int:
    """Mark in-flight jobs as interrupted after an engine restart."""
    now = utc_now()
    message = "Engine restarted before job completed"
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = 'interrupted', message = ?, updated_at = ?
            WHERE status IN ('running', 'pending')
            """,
            (message, now),
        )
        return int(cursor.rowcount)


def list_jobs_for_case(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE case_id = ? OR (case_id IS NULL AND result_json LIKE ?)
            ORDER BY created_at DESC
            """,
            (case_id, f'%"case_id": "{case_id}"%'),
        ).fetchall()
    jobs = []
    for row in rows:
        job = dict(row)
        if job.get("result_json"):
            try:
                job["result"] = json.loads(job["result_json"])
            except json.JSONDecodeError:
                job["result"] = None
        jobs.append(job)
    return jobs


def insert_sequence(
    device_id: str,
    *,
    channel: int,
    start_ts_raw: str | None = None,
    end_ts_raw: str | None = None,
    confidence: str,
    validation_level: str,
    output_path: str,
    output_md5: str,
    output_sha256: str,
    frame_count: int,
    drift_offset: float = 0,
    byte_start: int | None = None,
    byte_end: int | None = None,
    codec: str | None = None,
    offset_order: int | None = None,
    timestamp_source: str = "unavailable",
    timestamp_confidence: float | None = None,
    parser_name: str = "unknown",
    parser_version: str = "1",
    recovery_job_id: str | None = None,
    signature_evidence: dict | None = None,
    validation_evidence: dict | None = None,
) -> dict:
    seq_id = uuid.uuid4().hex

    def corrected(raw: str | None) -> str | None:
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return (parsed + timedelta(seconds=drift_offset)).isoformat().replace("+00:00", "Z")

    corrected_start = corrected(start_ts_raw)
    corrected_end = corrected(end_ts_raw)
    byte_length = max((byte_end or 0) - (byte_start or 0), 0) if byte_start is not None and byte_end is not None else None

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO recovered_sequences (
              id, device_id, channel, start_ts_raw, end_ts_raw, start_ts_corrected, end_ts_corrected,
              confidence, validation_level, output_path, output_md5, output_sha256, frame_count,
              byte_start, byte_end, byte_length, codec, recorder_start_ts, recorder_end_ts,
              corrected_start_ts, corrected_end_ts, offset_order, timestamp_source,
              timestamp_confidence, parser_name, parser_version, recovery_job_id, signature_evidence_json,
              validation_evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq_id,
                device_id,
                channel,
                start_ts_raw or "",
                end_ts_raw or "",
                corrected_start or "",
                corrected_end or "",
                confidence,
                validation_level,
                output_path,
                output_md5,
                output_sha256,
                frame_count,
                byte_start,
                byte_end,
                byte_length,
                codec,
                start_ts_raw,
                end_ts_raw,
                corrected_start,
                corrected_end,
                offset_order,
                timestamp_source,
                timestamp_confidence,
                parser_name,
                parser_version,
                recovery_job_id,
                json.dumps(signature_evidence or {}, sort_keys=True),
                json.dumps(validation_evidence or {}, sort_keys=True),
            ),
        )
        row = conn.execute("SELECT * FROM recovered_sequences WHERE id = ?", (seq_id,)).fetchone()
    return dict(row)


def list_sequences(device_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM recovered_sequences WHERE device_id = ? ORDER BY channel, offset_order, byte_start",
            (device_id,),
        ).fetchall()
    sequences = [dict(r) for r in rows]
    for sequence in sequences:
        for source, target in (
            ("signature_evidence_json", "signature_evidence"),
            ("validation_evidence_json", "validation_evidence"),
        ):
            try:
                sequence[target] = json.loads(sequence.get(source) or "{}")
            except json.JSONDecodeError:
                sequence[target] = {}
    return sequences


def delete_sequences_for_device(device_id: str) -> int:
    """Remove prior recovered segments and their artifact files for a device."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT output_path FROM recovered_sequences WHERE device_id = ?",
            (device_id,),
        ).fetchall()
        for row in rows:
            path = row["output_path"]
            if path:
                Path(path).unlink(missing_ok=True)
        cursor = conn.execute("DELETE FROM recovered_sequences WHERE device_id = ?", (device_id,))
        return int(cursor.rowcount)


def list_custody_for_case(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp_utc, actor, action, target_type, target_id,
                   prev_row_hash, this_row_hash, evidence_digest
            FROM custody_log WHERE target_type = 'case' AND target_id = ?
            ORDER BY id ASC
            """,
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def custody_status(case_id: str) -> dict:
    return verify_custody_chain("case", case_id)


def case_storage_dir(case_id: str) -> Path:
    path = CASES_DIR / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def update_device_acquisition(
    device_id: str,
    *,
    status: str,
    md5: str | None = None,
    sha256: str | None = None,
    bad_sector_map: dict | None = None,
    identification: dict | None = None,
    verification_status: str | None = None,
    completed: bool = False,
    acquisition_error: str | None = None,
) -> None:
    fields: list[str] = ["acquisition_status = ?"]
    values: list[Any] = [status]
    if md5 is not None:
        fields.append("image_md5 = ?")
        values.append(md5)
    if sha256 is not None:
        fields.append("image_sha256 = ?")
        values.append(sha256)
    if bad_sector_map is not None:
        fields.append("bad_sector_map_json = ?")
        values.append(json.dumps(bad_sector_map))
    if identification is not None:
        hits = identification.get("hits") or []
        fields.extend(["detection_trace_json = ?", "detected_engine = ?", "detection_confidence = ?", "declared_brand = ?"])
        values.extend(
            [
                json.dumps(identification),
                hits[0]["adapter"] if hits else None,
                hits[0]["confidence"] if hits else None,
                hits[0]["vendor"] if hits else None,
            ]
        )
    if verification_status is not None:
        fields.extend(["verification_status = ?", "verification_checked_at = ?"])
        values.extend([verification_status, utc_now()])
    if completed:
        fields.append("acquisition_completed_at = ?")
        values.append(utc_now())
    if acquisition_error is not None:
        fields.append("acquisition_error = ?")
        values.append(acquisition_error)
    values.append(device_id)
    with get_db() as conn:
        conn.execute(f"UPDATE devices SET {', '.join(fields)} WHERE id = ?", values)


def save_acquisition_checkpoint(device_id: str, bytes_written: int) -> None:
    blob = json.dumps({"bytes_written": bytes_written}).encode("utf-8")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO acquisition_checkpoints (device_id, bytes_written, running_md5_state, checkpoint_at)
            VALUES (?, ?, ?, ?)
            """,
            (device_id, bytes_written, blob, utc_now()),
        )


def get_latest_acquisition_checkpoint(device_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM acquisition_checkpoints
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
    return dict(row) if row else None


def list_resumable_devices(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM devices
            WHERE case_id = ? AND acquisition_status IN ('interrupted', 'in_progress', 'pending')
            ORDER BY acquired_at DESC
            """,
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_device_drift_offset(device_id: str, drift_offset_seconds: float) -> dict:
    with get_db() as conn:
        conn.execute(
            "UPDATE devices SET drift_offset_seconds = ? WHERE id = ?",
            (drift_offset_seconds, device_id),
        )
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if not row:
        raise ValueError("Device not found")
    return dict(row)


def reconcile_interrupted_acquisitions() -> int:
    """Mark in-flight acquisitions interrupted after engine restart."""
    now = utc_now()
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE devices
            SET acquisition_status = 'interrupted'
            WHERE acquisition_status IN ('in_progress', 'pending')
            """,
        )
        return int(cursor.rowcount)


def insert_ai_finding(
    sequence_id: str,
    *,
    frame_offset_ms: int,
    finding_type: str,
    label: str | None = None,
    confidence: float | None = None,
    bbox: dict | None = None,
) -> dict:
    finding_id = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO ai_findings (id, sequence_id, frame_offset_ms, finding_type, label, confidence, bbox_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                sequence_id,
                frame_offset_ms,
                finding_type,
                label,
                confidence,
                json.dumps(bbox) if bbox else None,
            ),
        )
        row = conn.execute("SELECT * FROM ai_findings WHERE id = ?", (finding_id,)).fetchone()
    return dict(row)


def list_ai_findings_for_device(device_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT f.* FROM ai_findings f
            JOIN recovered_sequences s ON s.id = f.sequence_id
            WHERE s.device_id = ?
            ORDER BY f.frame_offset_ms ASC
            """,
            (device_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        if item.get("bbox_json"):
            try:
                item["bbox"] = json.loads(item["bbox_json"])
            except json.JSONDecodeError:
                item["bbox"] = None
        out.append(item)
    return out


def delete_ai_findings_for_device(device_id: str) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            """
            DELETE FROM ai_findings
            WHERE sequence_id IN (SELECT id FROM recovered_sequences WHERE device_id = ?)
            """,
            (device_id,),
        )
        return int(cursor.rowcount)


def import_case_bundle_rows(
    case_row: dict,
    devices: list[dict],
    sequences: list[dict],
    custody_rows: list[dict],
    ai_findings: list[dict],
    *,
    actor: str,
) -> dict:
    """Insert an imported case preserving IDs and file paths under case storage."""
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM cases WHERE id = ?", (case_row["id"],)).fetchone()
        if existing:
            raise ValueError("Case ID already exists — import under a new bundle or delete the existing case")

        conn.execute(
            """
            INSERT INTO cases (id, name, examiner_name, created_at, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_row["id"],
                case_row["name"],
                case_row["examiner_name"],
                case_row["created_at"],
                case_row.get("notes"),
            ),
        )

        for device in devices:
            conn.execute(
                """
                INSERT INTO devices (
                  id, case_id, declared_brand, detected_engine, detection_confidence,
                  detection_trace_json, model_hint, serial_hint, image_path, image_md5, image_sha256,
                  acquisition_status, bad_sector_map_json, acquired_at, drift_offset_seconds,
                  source_type, source_identifier, source_size_bytes, acquisition_started_at,
                  acquisition_completed_at, acquisition_tool_version, acquisition_method,
                  write_blocker, acquisition_operator, acquisition_error,
                  verification_status, verification_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device["id"],
                    device["case_id"],
                    device.get("declared_brand"),
                    device.get("detected_engine"),
                    device.get("detection_confidence"),
                    device.get("detection_trace_json"),
                    device.get("model_hint"),
                    device.get("serial_hint"),
                    device["image_path"],
                    device.get("image_md5"),
                    device.get("image_sha256"),
                    device.get("acquisition_status", "complete"),
                    device.get("bad_sector_map_json"),
                    device.get("acquired_at"),
                    device.get("drift_offset_seconds") or 0,
                    device.get("source_type"),
                    device.get("source_identifier"),
                    device.get("source_size_bytes"),
                    device.get("acquisition_started_at"),
                    device.get("acquisition_completed_at"),
                    device.get("acquisition_tool_version"),
                    device.get("acquisition_method"),
                    device.get("write_blocker"),
                    device.get("acquisition_operator"),
                    device.get("acquisition_error"),
                    device.get("verification_status", "pending"),
                    device.get("verification_checked_at"),
                ),
            )

        for seq in sequences:
            conn.execute(
                """
                INSERT INTO recovered_sequences (
                  id, device_id, channel, start_ts_raw, end_ts_raw, start_ts_corrected, end_ts_corrected,
                  confidence, validation_level, output_path, output_md5, output_sha256, frame_count,
                  byte_start, byte_end, byte_length, codec, recorder_start_ts, recorder_end_ts,
                  corrected_start_ts, corrected_end_ts, offset_order, timestamp_source,
                  timestamp_confidence, parser_name, parser_version, recovery_job_id, signature_evidence_json,
                  validation_evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seq["id"],
                    seq["device_id"],
                    seq["channel"],
                    seq.get("start_ts_raw") or "",
                    seq.get("end_ts_raw") or "",
                    seq.get("start_ts_corrected") or "",
                    seq.get("end_ts_corrected") or "",
                    seq["confidence"],
                    seq["validation_level"],
                    seq["output_path"],
                    seq["output_md5"],
                    seq["output_sha256"],
                    seq["frame_count"],
                    seq.get("byte_start"),
                    seq.get("byte_end"),
                    seq.get("byte_length"),
                    seq.get("codec"),
                    seq.get("recorder_start_ts"),
                    seq.get("recorder_end_ts"),
                    seq.get("corrected_start_ts"),
                    seq.get("corrected_end_ts"),
                    seq.get("offset_order"),
                    seq.get("timestamp_source"),
                    seq.get("timestamp_confidence"),
                    seq.get("parser_name"),
                    seq.get("parser_version"),
                    seq.get("recovery_job_id"),
                    seq.get("signature_evidence_json") or json.dumps(seq.get("signature_evidence") or {}),
                    seq.get("validation_evidence_json") or json.dumps(seq.get("validation_evidence") or {}),
                ),
            )

        for entry in custody_rows:
            conn.execute(
                """
                INSERT INTO custody_log (
                  timestamp_utc, actor, action, target_type, target_id, prev_row_hash, this_row_hash, evidence_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["timestamp_utc"],
                    entry["actor"],
                    entry["action"],
                    entry["target_type"],
                    entry["target_id"],
                    entry["prev_row_hash"],
                    entry["this_row_hash"],
                    entry.get("evidence_digest"),
                ),
            )

        for finding in ai_findings:
            conn.execute(
                """
                INSERT INTO ai_findings (
                  id, sequence_id, frame_offset_ms, finding_type, label, confidence, bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding["id"],
                    finding["sequence_id"],
                    finding["frame_offset_ms"],
                    finding["finding_type"],
                    finding.get("label"),
                    finding.get("confidence"),
                    finding.get("bbox_json"),
                ),
            )

        append_custody(
            conn,
            actor=actor,
            action="case_imported",
            target_type="case",
            target_id=case_row["id"],
        )

        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_row["id"],)).fetchone()
    return dict(row)
