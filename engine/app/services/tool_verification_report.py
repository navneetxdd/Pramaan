from __future__ import annotations

import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from engine.app.core.config import APP_VERSION, REPORTS_DIR
from engine.app.core.db import get_db
from engine.app.core.signing import certificate_fingerprint, sign_pdf_bytes, signing_storage_backend


def _load_run(run_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, run_at, app_version, passed, results_json FROM tool_verification_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        raise ValueError("Verification run not found")
    item = dict(row)
    try:
        item["results"] = json.loads(item.pop("results_json"))
    except json.JSONDecodeError:
        item["results"] = {}
    return item


def _environment_block() -> dict:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "app_version": APP_VERSION,
        "signing_fingerprint": certificate_fingerprint(),
        "signing_storage": signing_storage_backend(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_json_report(run_id: str) -> dict:
    run = _load_run(run_id)
    results = run.get("results") or {}
    stages = results.get("stages") or []
    failures = [stage for stage in stages if not stage.get("passed")]
    return {
        "run_id": run_id,
        "run_at": run["run_at"],
        "app_version": run["app_version"],
        "passed": bool(run["passed"]),
        "stage_count": len(stages),
        "passed_count": sum(1 for stage in stages if stage.get("passed")),
        "failed_count": len(failures),
        "vendors_verified": results.get("vendors_verified") or [],
        "stages": stages,
        "failures": failures,
        "environment": _environment_block(),
        "methodology": (
            "Automated regression against generated known-answer specimens for Dahua, Honeywell, and Hikvision. "
            "This is not field validation on independent recorder media."
        ),
    }


def build_html_report(run_id: str) -> str:
    report = build_json_report(run_id)
    env = report["environment"]
    stage_rows = "".join(
        f"<tr><td>{escape(str(stage.get('stage', '')))}</td>"
        f"<td class=\"{'ok' if stage.get('passed') else 'bad'}\">{'PASS' if stage.get('passed') else 'FAIL'}</td>"
        f"<td><code>{escape(str(stage.get('detail', '')))}</code></td></tr>"
        for stage in report["stages"]
    )
    passed = report["passed"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Tool verification — {escape(run_id[:12])}</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;margin:2rem;background:#0a0e1a;color:#eef1f8}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}} th,td{{border:1px solid #2e3a5c;padding:8px;font-size:13px;text-align:left}}
th{{background:#161d30}} code{{font-family:monospace;font-size:12px;word-break:break-all}}
.ok{{color:#3ba676}} .bad{{color:#d6584f}}
.meta{{font-size:13px;line-height:1.6;color:#b8c0d4}}
</style></head><body>
<h1>Pramaan tool verification report</h1>
<p class="meta">Run <code>{escape(run_id)}</code> · {escape(str(report['run_at']))}</p>
<p>Overall result: <span class="{'ok' if passed else 'bad'}">{'PASS' if passed else 'FAIL'}</span> ·
Checks: {report['passed_count']}/{report['stage_count']}</p>
<h2>Environment</h2>
<ul class="meta">
<li>App version: {escape(str(env['app_version']))}</li>
<li>Platform: {escape(str(env['platform']))}</li>
<li>Python: {escape(str(env['python']))}</li>
<li>Signing fingerprint: <code>{escape(str(env['signing_fingerprint']))}</code></li>
<li>Signing storage: {escape(str(env['signing_storage']))}</li>
<li>Generated: {escape(str(env['generated_at']))}</li>
</ul>
<h2>Stage results</h2>
<table><tr><th>Stage</th><th>Result</th><th>Detail</th></tr>{stage_rows}</table>
<p class="meta">{escape(report['methodology'])}</p>
</body></html>"""


def build_pdf_report(run_id: str) -> tuple[bytes, str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    report = build_json_report(run_id)
    env = report["environment"]
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    y = height - 2 * cm

    def line(text: str, font: str = "Helvetica", size: int = 10) -> None:
        nonlocal y
        if y < 2 * cm:
            pdf.showPage()
            y = height - 2 * cm
        pdf.setFont(font, size)
        pdf.drawString(2 * cm, y, text[:110])
        y -= 0.45 * cm

    line("Pramaan Tool Verification Report", "Helvetica-Bold", 14)
    line(f"Run: {run_id}")
    line(f"Run at: {report['run_at']}")
    line(f"Result: {'PASS' if report['passed'] else 'FAIL'}")
    line(f"Checks: {report['passed_count']}/{report['stage_count']}")
    line(f"App version: {env['app_version']}")
    line(f"Platform: {env['platform']}")
    line(f"Python: {env['python']}")
    line(f"Signing fingerprint: {env['signing_fingerprint']}")
    line("Stage results:")
    for stage in report["stages"]:
        status = "PASS" if stage.get("passed") else "FAIL"
        line(f"  [{status}] {stage.get('stage', '')}: {str(stage.get('detail', ''))[:70]}")
    pdf.save()
    raw = buffer.getvalue()
    signed, fingerprint = sign_pdf_bytes(raw)
    output_path = REPORTS_DIR / f"tool_verification_{run_id}.pdf"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(signed)
    return signed, fingerprint
