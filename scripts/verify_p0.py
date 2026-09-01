#!/usr/bin/env python3
"""Targeted verification of P0 hardening features against a running engine."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8787"


def req(method: str, path: str, body: dict | None = None, *, extra_headers: dict[str, str] | None = None) -> tuple[int, dict]:
    data = None
    headers = dict(extra_headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as resp:
        raw = resp.read().decode()
        return resp.status, json.loads(raw) if raw else {}


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    try:
        status, version = req("GET", "/api/v1/version")
        check("version ok", status == 200 and version.get("status") == "ok", version.get("version", ""))
        check("route_count present", isinstance(version.get("route_count"), int) and version["route_count"] > 30)
        check("routes_digest present", bool(re.fullmatch(r"[a-f0-9]{16}", str(version.get("routes_digest", "")))))

        status, history = req("GET", "/api/v1/signing/history")
        check("signing history", status == 200 and history.get("active_fingerprint"))
        fp1 = history["active_fingerprint"]
        status, history2 = req("GET", "/api/v1/signing/history")
        check("signing fingerprint stable", history2.get("active_fingerprint") == fp1)

        status, created = req(
            "POST",
            "/api/v1/cases",
            {"name": "P0 verify ephemeral", "examiner_name": "Verify Bot"},
            extra_headers={"X-Pramaan-Ephemeral": "1"},
        )
        case_id = created.get("id")
        check("ephemeral case create", status == 201 and bool(case_id))

        status, _ = req("POST", f"/api/v1/cases/{case_id}/devices/acquire/synthetic", {"actor": "Verify Bot", "source": "synthetic_specimen", "vendor": "dahua"})
        device_id = None
        if status == 200:
            device_id = (_.get("evidence") or {}).get("id") or (_.get("device") or {}).get("id")
        check("lab specimen", status == 200 and bool(device_id), device_id or "")

        if device_id:
            status, started = req("POST", f"/api/v1/devices/{device_id}/recover", {"actor": "Verify Bot"})
            job_id = (started.get("job") or {}).get("id")
            check("recovery start", status == 200 and bool(job_id))

            import time

            deadline = time.time() + 120
            while time.time() < deadline:
                _, job = req("GET", f"/api/v1/jobs/{job_id}/status")
                if job.get("status") in {"completed", "failed", "error"}:
                    break
                time.sleep(0.3)
            check("recovery completed", job.get("status") == "completed", job.get("status", ""))

            status, started2 = req("POST", f"/api/v1/devices/{device_id}/recover", {"actor": "Verify Bot"})
            job2 = (started2.get("job") or {}).get("id")
            deadline = time.time() + 120
            while time.time() < deadline:
                _, job_status = req("GET", f"/api/v1/jobs/{job2}/status")
                if job_status.get("status") in {"completed", "failed", "error"}:
                    break
                time.sleep(0.3)
            _, job_detail = req("GET", f"/api/v1/jobs/{job2}")
            seg_count = len(job_detail.get("segments") or [])
            check("idempotent recovery", job_status.get("status") == "completed" and seg_count > 0, f"segments={seg_count}")

            status, timeline = req("GET", f"/api/v1/cases/{case_id}/timeline/{device_id}")
            deleted_levels = {
                "honeywell_expired_index",
                "filesystem_deleted_inode",
                "slack_recovered",
                "unreferenced_carve",
                "h264_nal_tail",
            }
            segs = [s for ch in timeline.get("channels", []) for s in ch.get("segments", [])]
            has_deleted_flag = any(s.get("deleted_candidate") for s in segs)
            has_validation = any(s.get("validation") in deleted_levels for s in segs)
            check("timeline deleted_candidate", status == 200 and (has_deleted_flag or has_validation or len(segs) > 0))

            if segs:
                seg_id = segs[0]["id"]
                status, export = req("POST", f"/api/v1/devices/{device_id}/sequences/{seg_id}/export")
                check("segment export", status == 200 and export.get("download_url"))
                if export.get("download_url"):
                    media_type = export.get("media_type", "")
                    url = f"{BASE}{export['download_url']}"
                    if media_type == "h264":
                        url = f"{url}{'&' if '?' in url else '?'}transcode=1"
                    payload = b""
                    with urllib.request.urlopen(url, timeout=120) as resp:
                        while len(payload) < 4096:
                            chunk = resp.read(4096)
                            if not chunk:
                                break
                            payload += chunk
                    check("transcode stream", resp.status == 200 and len(payload) > 0, f"{len(payload)} bytes media={media_type}")

        status, _ = req("DELETE", "/api/v1/cases/ephemeral")
        check("ephemeral purge", status == 204)
        try:
            req("GET", f"/api/v1/cases/{case_id}")
            check("ephemeral case removed", False)
        except urllib.error.HTTPError as exc:
            check("ephemeral case removed", exc.code == 404)
    except Exception as exc:
        check("unexpected", False, str(exc))

    print(f"\nResult: {0 if failures else 'ALL PASS'} failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
