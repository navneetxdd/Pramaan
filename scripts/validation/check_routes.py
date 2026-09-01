#!/usr/bin/env python3
"""Verify the engine exposes every expected /api/v1 route."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.app.main import app  # noqa: E402

EXPECTED = {
    "GET /api/v1/version",
    "GET /api/v1/cases",
    "POST /api/v1/cases",
    "GET /api/v1/signing/history",
    "DELETE /api/v1/cases/ephemeral",
    "DELETE /api/v1/cases/{case_id}",
    "GET /api/v1/cases/{case_id}",
    "GET /api/v1/cases/{case_id}/custody-log",
    "GET /api/v1/cases/{case_id}/custody-log/status",
    "GET /api/v1/cases/{case_id}/workspace",
    "GET /api/v1/cases/{case_id}/report",
    "GET /api/v1/cases/{case_id}/report.html",
    "GET /api/v1/cases/{case_id}/report.pdf",
    "GET /api/v1/cases/{case_id}/report/integrity",
    "GET /api/v1/cases/{case_id}/report/integrity.html",
    "GET /api/v1/cases/{case_id}/report/integrity.pdf",
    "POST /api/v1/cases/{case_id}/export",
    "POST /api/v1/cases/import",
    "GET /api/v1/acquisition/capabilities",
    "GET /api/v1/acquisition/disks",
    "POST /api/v1/cases/{case_id}/devices/acquire",
    "POST /api/v1/cases/{case_id}/devices/acquire/physical",
    "GET /api/v1/acquisition/oem-images",
    "POST /api/v1/cases/{case_id}/devices/acquire/oem",
    "POST /api/v1/cases/{case_id}/devices/acquire/logical",
    "POST /api/v1/cases/{case_id}/devices/acquire/synthetic",
    "GET /api/v1/cases/{case_id}/acquisition/resumable",
    "POST /api/v1/devices/{device_id}/acquire/resume",
    "POST /api/v1/jobs/{job_id}/cancel",
    "GET /api/v1/devices/{device_id}",
    "GET /api/v1/devices/{device_id}/verify",
    "GET /api/v1/devices/{device_id}/identification",
    "POST /api/v1/devices/{device_id}/drift-calibration",
    "GET /api/v1/devices/{device_id}/structure",
    "GET /api/v1/devices/{device_id}/bytes",
    "GET /api/v1/devices/{device_id}/bytes/find",
    "GET /api/v1/devices/{device_id}/sequences",
    "GET /api/v1/devices/{device_id}/sequences/{segment_id}",
    "GET /api/v1/devices/{device_id}/timeline",
    "POST /api/v1/devices/{device_id}/sequences/{segment_id}/export",
    "POST /api/v1/devices/{device_id}/recover",
    "POST /api/v1/devices/{device_id}/ai-analytics",
    "GET /api/v1/devices/{device_id}/ai-findings",
    "GET /api/v1/jobs/{job_id}",
    "GET /api/v1/jobs/{job_id}/events",
    "GET /api/v1/files/{filename}",
    "GET /api/v1/settings",
    "PUT /api/v1/settings",
    "GET /api/v1/tool-verification/results",
    "POST /api/v1/tool-verification/run",
    "GET /api/v1/datasets",
    "POST /api/v1/datasets/{dataset_id}/fetch",
}


def collect_routes() -> set[str]:
    found: set[str] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path or not str(path).startswith("/api/v1"):
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.add(f"{method} {path}")
    return found


def main() -> int:
    found = collect_routes()
    missing = sorted(EXPECTED - found)
    if missing:
        print("Missing routes:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK — {len(found)} /api/v1 routes registered ({len(EXPECTED)} required present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
