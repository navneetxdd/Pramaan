from __future__ import annotations

import uuid
from pathlib import Path

from pramaan.core.database import get_db, sha256_file, _utc_now
from pramaan.modules.custody.hash_chain import chain_seed, compute_event_hash


def _insert_custody(
    conn,
    case_id: str,
    actor: str,
    action: str,
    detail: str | None = None,
    image_id: str | None = None,
) -> None:
    now = _utc_now()
    last = conn.execute(
        """
        SELECT event_hash FROM custody_events
        WHERE case_id = ? AND event_hash IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """,
        (case_id,),
    ).fetchone()
    prev_hash = last["event_hash"] if last and last["event_hash"] else chain_seed(case_id)
    event_hash = compute_event_hash(prev_hash, action, actor, detail, now)
    conn.execute(
        """
        INSERT INTO custody_events
        (case_id, image_id, actor, action, detail, created_at, prev_hash, event_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (case_id, image_id, actor, action, detail, now, prev_hash, event_hash),
    )


def create_case(title: str, examiner: str, reference: str | None = None) -> dict:
    case_id = uuid.uuid4().hex
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO cases (id, title, examiner, reference, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'open', ?, ?)
            """,
            (case_id, title.strip(), examiner.strip(), reference, now, now),
        )
        _insert_custody(conn, case_id, examiner.strip(), "case_created", f"Case opened: {title.strip()}")
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row)


def list_cases() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_case(case_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def register_evidence(
    case_id: str,
    filename: str,
    storage_path: Path,
    actor: str,
    media_type: str = "disk_image",
) -> dict:
    image_id = uuid.uuid4().hex
    digest = sha256_file(storage_path)
    size_bytes = storage_path.stat().st_size
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO evidence_images
            (id, case_id, filename, storage_path, sha256, size_bytes, media_type, acquired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (image_id, case_id, filename, str(storage_path), digest, size_bytes, media_type, now),
        )
        _insert_custody(
            conn,
            case_id,
            actor,
            "evidence_acquired",
            f"SHA-256 {digest} · {size_bytes} bytes",
            image_id=image_id,
        )
        row = conn.execute("SELECT * FROM evidence_images WHERE id = ?", (image_id,)).fetchone()
    return dict(row)


def list_evidence(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM evidence_images WHERE case_id = ? ORDER BY acquired_at DESC",
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_custody(case_id: str, limit: int = 200) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM custody_events
            WHERE case_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (case_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def append_custody(
    case_id: str,
    actor: str,
    action: str,
    detail: str | None = None,
    image_id: str | None = None,
) -> None:
    with get_db() as conn:
        _insert_custody(conn, case_id, actor, action, detail, image_id=image_id)


def create_recovery_job(case_id: str, image_id: str) -> dict:
    job_id = uuid.uuid4().hex
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO recovery_jobs
            (id, case_id, image_id, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (job_id, case_id, image_id, now),
        )
        row = conn.execute("SELECT * FROM recovery_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


def complete_recovery_job(
    job_id: str,
    *,
    status: str,
    vendor: str | None,
    adapter: str | None,
    stats: dict,
    error: str | None = None,
) -> None:
    import json

    with get_db() as conn:
        conn.execute(
            """
            UPDATE recovery_jobs
            SET status = ?, vendor = ?, adapter = ?, stats_json = ?, error = ?, completed_at = ?
            WHERE id = ?
            """,
            (status, vendor, adapter, json.dumps(stats), error, _utc_now(), job_id),
        )


def insert_segment(
    job_id: str,
    *,
    channel: int | None,
    vendor: str,
    offset_start: int,
    offset_end: int,
    frame_count: int,
    confidence: float,
    validation: str,
    preview_path: str | None = None,
) -> dict:
    segment_id = uuid.uuid4().hex
    now = _utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO segments
            (id, job_id, channel, vendor, offset_start, offset_end, frame_count,
             confidence, validation, preview_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment_id,
                job_id,
                channel,
                vendor,
                offset_start,
                offset_end,
                frame_count,
                confidence,
                validation,
                preview_path,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM segments WHERE id = ?", (segment_id,)).fetchone()
    return dict(row)


def list_segments(job_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM segments WHERE job_id = ? ORDER BY offset_start ASC",
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM recovery_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs_for_case(case_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM recovery_jobs WHERE case_id = ? ORDER BY started_at DESC",
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def verify_image_integrity(image_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM evidence_images WHERE id = ?", (image_id,)).fetchone()
    if not row:
        raise ValueError("Evidence image not found")
    path = Path(row["storage_path"])
    if not path.exists():
        return {"ok": False, "reason": "file_missing", "expected": row["sha256"]}
    current = sha256_file(path)
    return {
        "ok": current == row["sha256"],
        "expected": row["sha256"],
        "actual": current,
    }
