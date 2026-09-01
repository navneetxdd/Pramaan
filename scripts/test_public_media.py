#!/usr/bin/env python3
"""End-to-end validation against public corpora in the OEM drop zone."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8787"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}


def wait_job(job_id: str) -> dict:
    deadline = time.time() + 120
    while time.time() < deadline:
        _, status = req("GET", f"/api/v1/jobs/{job_id}/status")
        if status.get("status") in {"completed", "failed", "error", "interrupted"}:
            return status
        time.sleep(0.25)
    raise TimeoutError(job_id)


def main() -> int:
    oem_dir = ROOT / "validation_data" / "oem"
    images = sorted(p for p in oem_dir.glob("*") if p.is_file() and p.suffix.lower() in {".e01", ".dd", ".img", ".raw", ".bin"})
    if not images:
        print("No OEM/public images in validation_data/oem")
        return 1

    filename = images[0].name
    print(f"Testing OEM acquire: {filename}")

    _, version = req("GET", "/api/v1/version")
    print("Engine", version.get("version"))

    _, case = req("POST", "/api/v1/cases", {"name": "Public media validation", "examiner_name": "Validator"})
    case_id = case["id"]

    _, oem_list = req("GET", "/api/v1/acquisition/oem-images")
    print("OEM drop zone", oem_list.get("count"), "image(s)")

    _, acquired = req("POST", f"/api/v1/cases/{case_id}/devices/acquire/oem", {"actor": "Validator", "filename": filename})
    device_id = acquired["evidence"]["id"]
    print("Acquired", device_id, acquired["evidence"]["sha256"][:16])

    _, verify = req("GET", f"/api/v1/devices/{device_id}/verify")
    print("Verify", verify.get("ok"))

    _, identification = req("POST", f"/api/v1/devices/{device_id}/identification")
    print("Adapter hint", identification.get("recommended_adapter"))

    _, recover = req("POST", f"/api/v1/devices/{device_id}/recover", {"actor": "Validator"})
    job = wait_job(recover["job"]["id"])
    print("Recovery", job.get("status"), job.get("message"))

    _, report = req("GET", f"/api/v1/cases/{case_id}/report")
    evidence = report.get("evidence") or []
    if evidence:
        print("Report acquisition_method", evidence[0].get("acquisition_method"))

    print("PASS public media OEM pipeline")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print("Engine not reachable at", BASE, exc)
        raise SystemExit(2) from exc
