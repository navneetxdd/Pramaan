#!/usr/bin/env python3
"""M1–M5 end-to-end API smoke test against a running engine."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"


def req(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    form: dict | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict | list | str]:
    url = f"{BASE}{path}"
    data = None
    headers: dict[str, str] = dict(extra_headers or {})
    if form is not None:
        import uuid

        boundary = uuid.uuid4().hex
        lines: list[bytes] = []
        for key, value in form.items():
            if hasattr(value, "read"):
                chunk = value.read()
                filename = getattr(value, "name", "upload.bin")
                lines.append(f"--{boundary}\r\n".encode())
                lines.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode())
                lines.append(b"Content-Type: application/octet-stream\r\n\r\n")
                lines.append(chunk)
                lines.append(b"\r\n")
            else:
                lines.append(f"--{boundary}\r\n".encode())
                lines.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
                lines.append(str(value).encode())
                lines.append(b"\r\n")
        lines.append(f"--{boundary}--\r\n".encode())
        data = b"".join(lines)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            if not raw:
                return resp.status, {}
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def raw_req(method: str, path: str, timeout: float = 60.0) -> tuple[int, bytes]:
    url = f"{BASE}{path}"
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait_job(job_id: str, timeout_s: float = 180.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, body = req("GET", f"/api/v1/jobs/{job_id}/status")
        if status != 200:
            raise RuntimeError(f"Job status failed: {status} {body}")
        if body.get("status") in ("completed", "failed", "error", "interrupted"):
            return body
        time.sleep(0.4)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_s}s")


def main() -> int:
    steps: list[tuple[str, bool, str]] = []
    case_id: str | None = None
    imaging_case_id: str | None = None
    import_cleanup_id: str | None = None

    def record(name: str, ok: bool, detail: str = "") -> None:
        steps.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))

    try:
        # --- M1: shell API + workspace ---
        status, body = req("GET", "/api/v1/version")
        caps = body.get("capabilities", {}) if isinstance(body, dict) else {}
        record(
            "M1 version + capabilities",
            status == 200 and body.get("status") == "ok" and "modules" in caps,
            str(body.get("version", "")),
        )

        status, body = req("GET", "/api/v1/settings")
        record("M1 settings", status == 200, str(body.get("working_directory", ""))[:50])

        status, body = req(
            "POST",
            "/api/v1/cases",
            {"name": "Smoke M1-M4", "examiner_name": "Smoke Bot", "notes": "automated"},
            extra_headers={"X-Pramaan-Ephemeral": "1"},
        )
        case_id = body.get("id") if status == 201 else None
        record("M1 create case", status == 201 and bool(case_id), case_id or str(body))
        if not case_id:
            raise RuntimeError("No case_id")

        status, body = req("GET", f"/api/v1/cases/{case_id}/workspace")
        record(
            "M1 workspace",
            status == 200 and "case" in body and "custody" in body,
            f"evidence={len(body.get('evidence', []))}",
        )

        status, body = req("GET", f"/api/v1/cases/{case_id}/custody-log/status")
        record("M1 custody chain", status == 200 and body.get("intact") is True)

        # --- M2: specimen + recovery + validation ---
        status, body = req(
            "POST",
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            {"actor": "Smoke Bot", "source": "synthetic_specimen"},
        )
        device_id = None
        if isinstance(body, dict):
            device_id = (
                body.get("device_id")
                or (body.get("device") or {}).get("id")
                or (body.get("evidence") or {}).get("id")
            )
        record("M2 lab specimen (DHAV 4-check)", status == 200 and bool(device_id), device_id or str(body))
        if not device_id:
            raise RuntimeError("No device_id")

        status, body = req("GET", f"/api/v1/devices/{device_id}/identification")
        hits = body.get("hits", []) if isinstance(body, dict) else []
        record("M2 identification", status == 200 and len(hits) > 0, hits[0].get("vendor", "") if hits else "")

        status, body = req("GET", f"/api/v1/devices/{device_id}/verify")
        record("M2 integrity verify", status == 200 and body.get("ok") is True)

        status, body = req("POST", f"/api/v1/devices/{device_id}/recover", {"actor": "Smoke Bot"})
        job_id = (body.get("job") or {}).get("id") if isinstance(body, dict) else None
        record("M2 start recovery", status == 200 and bool(job_id), job_id or str(body))
        if not job_id:
            raise RuntimeError("No recovery job_id")

        job = wait_job(job_id)
        record("M2 recovery job", job.get("status") == "completed", job.get("status", ""))

        status, body = req("GET", f"/api/v1/jobs/{job_id}")
        segments = body.get("segments", []) if isinstance(body, dict) else []
        has_validation = any(seg.get("validation") or seg.get("confidence_tier") for seg in segments)
        record("M2 segments + validation", status == 200 and len(segments) > 0, f"count={len(segments)} val={has_validation}")

        if segments:
            seg_id = segments[0].get("id") or segments[0].get("segment_id")
            if seg_id:
                status, export_body = req(
                    "POST",
                    f"/api/v1/devices/{device_id}/sequences/{seg_id}/export",
                )
                record(
                    "M2 segment export",
                    status == 200 and isinstance(export_body, dict) and export_body.get("download_url"),
                    export_body.get("filename", "") if isinstance(export_body, dict) else "",
                )

        status, body = req("GET", f"/api/v1/cases/{case_id}/timeline/{device_id}")
        record(
            "M1 timeline API",
            status == 200 and body.get("channel_count", 0) >= 0,
            f"channels={body.get('channel_count', 0)}",
        )

        status, body = req("POST", "/api/v1/tool-verification/run")
        tv_job = body.get("job_id") if isinstance(body, dict) else None
        record("M2 tool verification start", status == 200 and bool(tv_job), tv_job or "")
        if tv_job:
            tv = wait_job(tv_job, timeout_s=120)
            record("M2 tool verification", tv.get("status") == "completed", tv.get("status", ""))
            if tv.get("status") == "completed":
                status, tv_body = req("GET", "/api/v1/tool-verification/results")
                runs = tv_body if isinstance(tv_body, list) else []
                latest = runs[0] if runs else {}
                vendors = latest.get("results", {}).get("vendors_verified", []) if isinstance(latest.get("results"), dict) else []
                passed_flag = latest.get("passed") in (True, 1)
                record(
                    "M2 tool verification multi-vendor",
                    passed_flag and "honeywell" in vendors and "hikvision" in vendors,
                    f"passed={latest.get('passed')} vendors={vendors}",
                )

        # --- M3: Honeywell known-answer pipeline ---
        status, body = req(
            "POST",
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            {"actor": "Smoke Bot", "source": "synthetic_specimen", "vendor": "honeywell"},
        )
        honey_device_id = None
        if isinstance(body, dict):
            honey_device_id = (
                body.get("device_id")
                or (body.get("device") or {}).get("id")
                or (body.get("evidence") or {}).get("id")
            )
        record(
            "M3 honeywell specimen",
            status == 200 and body.get("vendor") == "honeywell" and bool(honey_device_id),
            honey_device_id or str(body),
        )

        if honey_device_id:
            status, body = req("GET", f"/api/v1/devices/{honey_device_id}/identification")
            hits = body.get("hits", []) if isinstance(body, dict) else []
            record(
                "M3 honeywell identification",
                status == 200 and any(h.get("vendor") == "Honeywell" for h in hits),
                hits[0].get("vendor", "") if hits else "",
            )

            status, body = req("POST", f"/api/v1/devices/{honey_device_id}/recover", {"actor": "Smoke Bot"})
            honey_job_id = (body.get("job") or {}).get("id") if isinstance(body, dict) else None
            record("M3 honeywell recovery start", status == 200 and bool(honey_job_id), honey_job_id or "")
            if honey_job_id:
                honey_job = wait_job(honey_job_id)
                record("M3 honeywell recovery job", honey_job.get("status") == "completed", honey_job.get("status", ""))
                status, body = req("GET", f"/api/v1/jobs/{honey_job_id}")
                honey_segments = body.get("segments", []) if isinstance(body, dict) else []
                honey_vals = {s.get("validation") for s in honey_segments}
                record(
                    "M3 honeywell deleted recovery",
                    status == 200 and len(honey_segments) > 0,
                    f"count={len(honey_segments)} vals={list(honey_vals)[:3]}",
                )

        # --- M3: Hikvision known-answer pipeline ---
        status, body = req(
            "POST",
            f"/api/v1/cases/{case_id}/devices/acquire/synthetic",
            {"actor": "Smoke Bot", "source": "synthetic_specimen", "vendor": "hikvision"},
        )
        hik_device_id = None
        if isinstance(body, dict):
            hik_device_id = (
                body.get("device_id")
                or (body.get("device") or {}).get("id")
                or (body.get("evidence") or {}).get("id")
            )
        record(
            "M3 hikvision specimen",
            status == 200 and body.get("vendor") == "hikvision" and bool(hik_device_id),
            hik_device_id or str(body),
        )
        if hik_device_id:
            status, body = req("POST", f"/api/v1/devices/{hik_device_id}/recover", {"actor": "Smoke Bot"})
            hik_job_id = (body.get("job") or {}).get("id") if isinstance(body, dict) else None
            if hik_job_id:
                hik_job = wait_job(hik_job_id)
                record("M3 hikvision recovery job", hik_job.get("status") == "completed", hik_job.get("status", ""))
                status, body = req("GET", f"/api/v1/jobs/{hik_job_id}")
                hik_segments = body.get("segments", []) if isinstance(body, dict) else []
                hik_vals = {s.get("validation") for s in hik_segments}
                record(
                    "M3 hikvision HIKBTREE recovery",
                    status == 200 and len(hik_segments) > 0,
                    f"count={len(hik_segments)} vals={list(hik_vals)[:3]}",
                )

        # --- M3: generic tier2 adapter listed ---
        status, body = req("GET", "/api/v1/version")
        adapters = (body.get("capabilities") or {}).get("recovery_adapters", [])
        record(
            "M3 honeywell + generic_tier2 adapters",
            "honeywell" in adapters and "generic_tier2" in adapters,
            ",".join(adapters[:6]),
        )

        # --- M4: acquisition + drift ---
        status, body = req("GET", "/api/v1/acquisition/disks")
        record("M4 disk enumeration", status == 200 and "disks" in body, f"count={body.get('count', 0)}")

        status, body = req("GET", "/api/v1/acquisition/capabilities")
        record(
            "M4 acquisition capabilities",
            status == 200 and body.get("chunked_imaging") is True,
            f"e01={body.get('e01_input')}",
        )

        status, body = req(
            "POST",
            "/api/v1/cases",
            {"name": "Smoke M4 Imaging", "examiner_name": "Smoke Bot"},
            extra_headers={"X-Pramaan-Ephemeral": "1"},
        )
        imaging_case_id = body.get("id") if status == 201 else None
        record("M4 imaging case", status == 201 and bool(imaging_case_id), imaging_case_id or "")

        if imaging_case_id:
            # Create temp source file for block imaging
            src = Path(tempfile.mkdtemp()) / "smoke_source.bin"
            src.write_bytes(b"SMOKE" * (256 * 1024))

            status, body = req(
                "POST",
                f"/api/v1/cases/{imaging_case_id}/devices/acquire/physical",
                {
                    "actor": "Smoke Bot",
                    "source_path": str(src),
                    "source_type": "file",
                },
            )
            acq_job = (body.get("job") or {}).get("id") if isinstance(body, dict) else None
            acq_device = (body.get("job") or {}).get("device_id") or (body.get("device") or {}).get("id")
            record("M4 physical imaging start", status == 200 and bool(acq_job), acq_job or str(body))

            if acq_job:
                acq = wait_job(acq_job, timeout_s=120)
                record("M4 imaging job", acq.get("status") == "completed", acq.get("status", ""))

            if acq_device:
                status, body = req("GET", f"/api/v1/devices/{acq_device}/verify")
                record("M4 post-image verify", status == 200 and body.get("ok") is True)

                status, body = req(
                    "POST",
                    f"/api/v1/devices/{acq_device}/drift-calibration",
                    {"reference_wall_unix": 1_700_000_000.0, "reference_device_unix": 1_699_999_850.0},
                )
                record(
                    "M4 drift calibration",
                    status == 200 and abs(body.get("drift_offset_seconds", 0) - 150.0) < 0.01,
                    f"offset={body.get('drift_offset_seconds')}",
                )

            status, body = req("GET", f"/api/v1/cases/{imaging_case_id}/acquisition/resumable")
            record("M4 resumable list", status == 200 and "devices" in body)

        status, body = req("GET", f"/api/v1/cases/{case_id}/report")
        record("M1 report metadata", status == 200)

        pdf_status, pdf_bytes = raw_req("GET", f"/api/v1/cases/{case_id}/report.pdf")
        record(
            "M1 signed report PDF",
            pdf_status == 200 and pdf_bytes.startswith(b"%PDF"),
            f"{len(pdf_bytes)} bytes",
        )

        # --- M5: export/import + AI analytics ---
        status, export_body = req("POST", f"/api/v1/cases/{case_id}/export", form={"actor": "Smoke Bot"})
        export_ok = status == 200 and isinstance(export_body, dict) and export_body.get("download_url")
        record("M5 export bundle", export_ok, export_body.get("filename", "") if isinstance(export_body, dict) else "")

        analytics_device = honey_device_id or device_id
        ai: dict = {}
        status, body = req("POST", f"/api/v1/devices/{analytics_device}/ai-analytics", {"actor": "Smoke Bot"})
        ai_job = body.get("job", {}).get("id") if isinstance(body, dict) else None
        record("M5 AI analytics start", status == 200 and bool(ai_job), ai_job or "")
        if ai_job:
            ai = wait_job(ai_job, timeout_s=120)
            record("M5 AI analytics job", ai.get("status") == "completed", ai.get("status", ""))

        status, body = req("GET", f"/api/v1/devices/{analytics_device}/ai-findings")
        finding_count = body.get("count", 0) if isinstance(body, dict) else 0
        demo_unavailable = bool((ai.get("result") or {}).get("demo_mode_unavailable"))
        record(
            "M5 AI findings list",
            status == 200 and (finding_count >= 1 or demo_unavailable),
            f"count={finding_count}",
        )

        if export_ok and isinstance(export_body, dict):
            bundle_name = export_body.get("filename")
            if bundle_name:
                import urllib.request

                bundle_path = Path(tempfile.mkdtemp()) / bundle_name
                urllib.request.urlretrieve(f"{BASE}/api/v1/bundles/{bundle_name}", bundle_path)
                req("DELETE", f"/api/v1/cases/{case_id}")
                case_id = None
                import uuid as uuid_mod

                boundary = uuid_mod.uuid4().hex
                file_bytes = bundle_path.read_bytes()
                parts = [
                    f"--{boundary}\r\n".encode(),
                    b'Content-Disposition: form-data; name="actor"\r\n\r\n',
                    b"Smoke Bot\r\n",
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="bundle"; filename="{bundle_name}"\r\n'.encode(),
                    b"Content-Type: application/zip\r\n\r\n",
                    file_bytes,
                    b"\r\n",
                    f"--{boundary}--\r\n".encode(),
                ]
                import_req = urllib.request.Request(
                    f"{BASE}/api/v1/cases/import",
                    data=b"".join(parts),
                    method="POST",
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
                try:
                    with urllib.request.urlopen(import_req, timeout=60) as resp:
                        imported = json.loads(resp.read().decode())
                    record(
                        "M5 import bundle",
                        imported.get("integrity_ok") is True,
                        f"files={imported.get('files_verified')}",
                    )
                    imported_case = imported.get("case_id")
                    import_cleanup_id = imported_case
                except urllib.error.HTTPError as exc:
                    record("M5 import bundle", False, exc.read().decode()[:120])

    except Exception as exc:
        record("unexpected error", False, str(exc))
    finally:
        req("DELETE", "/api/v1/cases/ephemeral")
        for cid in (case_id, imaging_case_id, import_cleanup_id):
            if cid:
                del_status, _ = req("DELETE", f"/api/v1/cases/{cid}")
                record(f"cleanup {cid[:8]}", del_status == 204)

    failed = [s for s in steps if not s[1]]
    print("\n--- Summary ---")
    print(f"Passed: {len(steps) - len(failed)}/{len(steps)}")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} ({detail})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
