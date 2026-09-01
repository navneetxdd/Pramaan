from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from engine.app.api.v1.models import (
    Case,
    CaseCreate,
    CaseDetail,
    CustodyLogEntry,
    CustodyLogStatus,
    Device,
)
from engine.app.core.db import append_custody, get_db, utc_now, verify_custody_chain
from engine.app.core.repository import (
    custody_status,
    delete_case as repo_delete_case,
    delete_ephemeral_cases as repo_delete_ephemeral_cases,
    get_case as repo_get_case,
    get_device as repo_get_device,
    list_custody_for_case,
    list_devices,
    list_jobs_for_case,
)
from engine.app.services.acquisition import _device_as_evidence
from engine.app.services.timeline import build_timeline_for_device

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_from_row(row: dict) -> Case:
    return Case(
        id=row["id"],
        name=row["name"],
        examiner_name=row["examiner_name"],
        created_at=row["created_at"],
        notes=row["notes"],
        ephemeral=bool(row.get("ephemeral")),
    )


def _device_from_row(row: dict) -> Device:
    return Device(
        id=row["id"],
        case_id=row["case_id"],
        declared_brand=row["declared_brand"],
        detected_engine=row["detected_engine"],
        detection_confidence=row["detection_confidence"],
        detection_trace_json=row["detection_trace_json"],
        model_hint=row["model_hint"],
        serial_hint=row["serial_hint"],
        image_path=row["image_path"],
        image_md5=row["image_md5"],
        image_sha256=row["image_sha256"],
        acquisition_status=row["acquisition_status"],
        bad_sector_map_json=row["bad_sector_map_json"],
        acquired_at=row["acquired_at"],
        drift_offset_seconds=row["drift_offset_seconds"] or 0,
    )


@router.post("", response_model=Case, status_code=201)
def create_case(body: CaseCreate, request: Request) -> Case:
    case_id = uuid.uuid4().hex
    created_at = utc_now()
    ephemeral = request.headers.get("X-Pramaan-Ephemeral", "").strip() == "1"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO cases (id, name, examiner_name, created_at, notes, ephemeral)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (case_id, body.name.strip(), body.examiner_name.strip(), created_at, body.notes, 1 if ephemeral else 0),
        )
        append_custody(
            conn,
            actor=body.examiner_name.strip(),
            action="case_created",
            target_type="case",
            target_id=case_id,
        )
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return _case_from_row(dict(row))


@router.get("", response_model=list[Case])
def list_cases(include_automated: bool = False) -> list[Case]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    cases = [_case_from_row(dict(row)) for row in rows]
    if include_automated:
        return cases
    return [case for case in cases if not case.ephemeral and not _is_automated_case_name(case.name)]


def _is_automated_case_name(name: str) -> bool:
    import re

    patterns = (
        r"^M\d[\s_]",
        r"^Smoke[\s_]",
        r"^Custody gate$",
        r"^Tool Verification$",
        r"^verify_",
        r"^Public media validation$",
        r"^CAVIAR analytics$",
        r"^E01 OEM$",
        r"^M5 Export$",
        r"^dbg$",
    )
    stripped = name.strip()
    return any(re.match(pattern, stripped, re.I) for pattern in patterns)


class CaseRegistryEntry(Case):
    evidence_count: int = 0
    total_bytes: int = 0
    recovery_jobs: int = 0


@router.get("/registry", response_model=list[CaseRegistryEntry])
def list_case_registry() -> list[CaseRegistryEntry]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
        out: list[CaseRegistryEntry] = []
        for row in rows:
            base = _case_from_row(dict(row))
            if base.ephemeral or _is_automated_case_name(base.name):
                continue
            stats = conn.execute(
                """
                SELECT COUNT(*) AS evidence_count,
                       COALESCE(SUM(source_size_bytes), 0) AS total_bytes
                FROM devices WHERE case_id = ?
                """,
                (base.id,),
            ).fetchone()
            jobs = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE case_id = ? AND kind = 'recovery'",
                (base.id,),
            ).fetchone()
            out.append(
                CaseRegistryEntry(
                    **base.model_dump(),
                    evidence_count=int(stats["evidence_count"] or 0),
                    total_bytes=int(stats["total_bytes"] or 0),
                    recovery_jobs=int(jobs["n"] or 0),
                )
            )
    return out


@router.delete("/ephemeral", status_code=204, response_class=Response)
def delete_ephemeral_cases() -> Response:
    repo_delete_ephemeral_cases()
    return Response(status_code=204)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Case not found")
        devices = conn.execute(
            "SELECT * FROM devices WHERE case_id = ? ORDER BY acquired_at DESC NULLS LAST",
            (case_id,),
        ).fetchall()
    base = _case_from_row(dict(row))
    return CaseDetail(**base.model_dump(), devices=[_device_from_row(dict(d)) for d in devices])


@router.delete("/{case_id}", status_code=204, response_class=Response)
def delete_case(case_id: str) -> Response:
    if not repo_delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    return Response(status_code=204)


@router.get("/{case_id}/custody-log", response_model=list[CustodyLogEntry])
def get_custody_log(case_id: str) -> list[CustodyLogEntry]:
    with get_db() as conn:
        case = conn.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        rows = conn.execute(
            """
            SELECT id, timestamp_utc, actor, action, target_type, target_id, prev_row_hash, this_row_hash
            FROM custody_log
            WHERE target_type = 'case' AND target_id = ?
            ORDER BY id ASC
            """,
            (case_id,),
        ).fetchall()
    return [CustodyLogEntry(**dict(row)) for row in rows]


@router.get("/{case_id}/custody-log/status", response_model=CustodyLogStatus)
def get_custody_status(case_id: str) -> CustodyLogStatus:
    with get_db() as conn:
        case = conn.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
    status = verify_custody_chain("case", case_id)
    return CustodyLogStatus(**status)


@router.get("/{case_id}/workspace")
def get_case_workspace(case_id: str) -> dict:
    case = repo_get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    devices = list_devices(case_id)
    evidence = [_device_as_evidence(d) for d in devices]
    jobs: list[dict] = []
    for job in list_jobs_for_case(case_id):
        jobs.append(
            {
                "id": job["id"],
                "case_id": case_id,
                "image_id": job.get("device_id") or (job.get("result") or {}).get("device_id", ""),
                "device_id": job.get("device_id"),
                "kind": job.get("kind"),
                "status": job["status"],
                "vendor": (job.get("result") or {}).get("vendor"),
                "adapter": (job.get("result") or {}).get("adapter"),
                "stats_json": job.get("result_json"),
                "error": job.get("error"),
                "started_at": job["created_at"],
                "completed_at": job["updated_at"],
            }
        )

    custody = [
        {
            "id": entry["id"],
            "case_id": entry["target_id"],
            "image_id": None,
            "actor": entry["actor"],
            "action": entry["action"],
            "detail": entry.get("target_type"),
            "created_at": entry["timestamp_utc"],
        }
        for entry in list_custody_for_case(case_id)
    ]
    chain = custody_status(case_id)
    return {
        "case": {
            "id": case["id"],
            "name": case["name"],
            "examiner_name": case["examiner_name"],
            "notes": case.get("notes"),
            "status": case.get("status", "open"),
            "created_at": case["created_at"],
            "updated_at": case.get("updated_at", case["created_at"]),
            "ephemeral": bool(case.get("ephemeral")),
        },
        "evidence": evidence,
        "jobs": jobs,
        "custody": custody,
        "chain": {"ok": chain["intact"], **chain},
    }


@router.get("/{case_id}/timeline/{device_id}")
def case_device_timeline(case_id: str, device_id: str) -> dict:
    if not repo_get_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    device = repo_get_device(device_id)
    if not device or device.get("case_id") != case_id:
        raise HTTPException(status_code=404, detail="Device not found in this case")
    try:
        return build_timeline_for_device(device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
