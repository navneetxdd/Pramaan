#!/usr/bin/env python3
"""OEM acquire smoke for Digital Corpora E01 (requires pyewf / libewf-python)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8787"
FILENAME = "nps-2009-canon2-gen6.E01"


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    case = req("POST", "/api/v1/cases", {"name": "E01 OEM", "examiner_name": "Validator"})["id"]
    acquired = req("POST", f"/api/v1/cases/{case}/devices/acquire/oem", {"actor": "Validator", "filename": FILENAME})
    device_id = acquired["evidence"]["id"]
    print("Acquired E01", device_id, acquired["evidence"]["size_bytes"], "bytes")
    verify = req("GET", f"/api/v1/devices/{device_id}/verify")
    print("Verify", verify.get("ok"))
    identification = req("POST", f"/api/v1/devices/{device_id}/identification")
    print("Adapter", identification.get("recommended_adapter"))
    print("PASS E01 OEM acquire")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print("Engine not reachable:", exc)
        raise SystemExit(2) from exc
