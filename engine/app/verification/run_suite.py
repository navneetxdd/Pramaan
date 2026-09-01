from __future__ import annotations

import json
import uuid

from engine.app.core.config import APP_VERSION
from engine.app.core.db import get_db, utc_now
from engine.app.core.job_manager import job_manager
from engine.app.core.repository import case_storage_dir, list_sequences, register_device_from_path
from engine.app.parsers.manufacturer_detect import identify_image
from engine.app.parsers.registry import bootstrap_defaults
from engine.app.services.recovery import run_recovery_job
from engine.app.services.acquisition import create_lab_specimen
from engine.app.core.config import VALIDATION_DATA_DIR
from engine.app.verification.playable_checks import _playable_export_stage, dahua_real_dav_stage


async def _vendor_stages(
    case_id: str,
    actor: str,
    vendor: str,
    expected_vendors: set[str],
) -> tuple[list[dict], str | None]:
    """Acquire known-answer specimen, run recovery, return stage results and device id."""
    result = await create_lab_specimen(case_id, actor, vendor=vendor)
    device = result["evidence"]
    device_id = device["id"]
    dest = case_storage_dir(case_id)
    specimen_name = {
        "honeywell": "lab_honeywell_specimen.bin",
        "hikvision": "lab_hikvision_specimen.bin",
        "dahua": "lab_dahua_dhav_specimen.bin",
    }.get(vendor, "lab_dahua_dhav_specimen.bin")
    specimen_path = dest / specimen_name

    stages: list[dict] = []
    stages.append(
        {
            "stage": f"{vendor}_fixture_integrity",
            "passed": specimen_path.exists() and specimen_path.stat().st_size > 1024,
            "detail": f"{specimen_path.stat().st_size} bytes",
        }
    )

    hits = (result.get("identification") or {}).get("hits") or []
    stages.append(
        {
            "stage": f"{vendor}_manufacturer_detection",
            "passed": any(h.get("vendor") in expected_vendors for h in hits),
            "detail": json.dumps(hits[:3]),
        }
    )

    recovery_job = await job_manager.create("recovery")
    await run_recovery_job(
        recovery_job.id,
        case_id,
        device_id,
        actor,
        max_scan_bytes=None,
        min_sequence_frames=3,
    )
    sequences = list_sequences(device_id)
    validations = sorted({s.get("validation_level") or "" for s in sequences if s.get("validation_level")})
    playable = _playable_export_stage(device_id, sequences)
    stages.append(
        {
            "stage": f"{vendor}_recovery_pipeline",
            "passed": len(sequences) > 0 and playable["passed"],
            "detail": f"{len(sequences)} sequences · validations={validations[:4]} · {playable['detail']}",
        }
    )
    if vendor == "dahua":
        stages.append(playable)
    return stages, device_id


async def run_verification_suite(job_id: str) -> dict:
    bootstrap_defaults()
    case_id = f"verify_{uuid.uuid4().hex[:8]}"
    actor = "System"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO cases (id, name, examiner_name, created_at, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case_id, "Tool Verification", actor, utc_now(), "Automated CFTT-style self-test"),
        )

    stages: list[dict] = []

    dahua_stages, _ = await _vendor_stages(
        case_id,
        actor,
        "dahua",
        {"Dahua", "CP Plus"},
    )
    stages.extend(dahua_stages)

    honeywell_stages, _ = await _vendor_stages(
        case_id,
        actor,
        "honeywell",
        {"Honeywell"},
    )
    stages.extend(honeywell_stages)

    hikvision_stages, _ = await _vendor_stages(
        case_id,
        actor,
        "hikvision",
        {"Hikvision", "Uniview"},
    )
    stages.extend(hikvision_stages)

    real_dav = VALIDATION_DATA_DIR / "external" / "dvr" / "dahua" / "19.25.00-19.25.50-R-.dav"
    stages.append(dahua_real_dav_stage(real_dav))

    passed = all(s["passed"] for s in stages)
    results = {
        "stages": stages,
        "passed": passed,
        "app_version": APP_VERSION,
        "vendors_verified": ["dahua", "honeywell", "hikvision"],
    }
    run_id = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO tool_verification_runs (id, run_at, app_version, passed, results_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, utc_now(), APP_VERSION, passed, json.dumps(results)),
        )
    return {"run_id": run_id, **results}
