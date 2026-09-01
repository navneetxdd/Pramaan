from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from engine.app.core.config import APP_VERSION, REPORTS_DIR
from engine.app.core.db import append_custody, get_db
from engine.app.core.repository import (
    custody_status,
    get_case,
    list_custody_for_case,
    list_devices,
    list_jobs_for_case,
    list_sequences,
)
from engine.app.core.signing import sign_pdf_bytes


def _recovery_summary(case_id: str) -> list[dict]:
    summary: list[dict] = []
    for job in list_jobs_for_case(case_id):
        if job.get("kind") != "recovery":
            continue
        result = job.get("result") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {}
        adapter = result.get("adapter")
        segment_count = int(result.get("segments_found") or 0)
        if not adapter and segment_count == 0:
            continue
        summary.append(
            {
                "job_id": job["id"],
                "status": job["status"],
                "vendor": result.get("vendor"),
                "adapter": adapter,
                "segment_count": segment_count,
                "segment_evidence": result.get("evidence", []),
            }
        )
    for device in list_devices(case_id):
        sequences = list_sequences(device["id"])
        summary.append(
            {
                "summary_type": "current_sequences",
                "device_id": device["id"],
                "vendor": device.get("declared_brand"),
                "adapter": device.get("detected_engine"),
                "segment_count": len(sequences),
                "segment_evidence": [
                    {
                        "sequence_id": sequence["id"],
                        "byte_start": sequence.get("byte_start"),
                        "byte_end": sequence.get("byte_end"),
                        "byte_length": sequence.get("byte_length"),
                        "offset_order": sequence.get("offset_order"),
                        "parser_name": sequence.get("parser_name"),
                        "parser_version": sequence.get("parser_version"),
                        "signature_evidence": sequence.get("signature_evidence", {}),
                        "validation_evidence": sequence.get("validation_evidence", {}),
                    }
                    for sequence in sequences
                ],
            }
        )
    return summary


def build_json_report(case_id: str, *, require_intact_chain: bool = True) -> dict:
    case = get_case(case_id)
    if not case:
        raise ValueError("Case not found")
    custody = list_custody_for_case(case_id)
    chain = custody_status(case_id)
    if require_intact_chain and not chain["intact"]:
        raise ValueError(f"Custody chain broken at row {chain.get('first_broken_row_id')}")
    devices = list_devices(case_id)
    recovery = _recovery_summary(case_id)
    return {
        "case": _case_legacy_shape(case),
        "evidence_count": len(devices),
        "evidence": [_device_report_row(d) for d in devices],
        "recovery_summary": recovery,
        "total_segments_recovered": sum(item["segment_count"] for item in recovery),
        "custody_events": [_custody_legacy(e) for e in custody],
        "custody_chain_valid": {"ok": chain["intact"], **chain},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Forensic Workstation",
        "app_version": APP_VERSION,
        "methodology": "Tier 1 dual-signature DHAV/HKVI + Tier 2 H.264 carve (SIH26150)",
        "report_kind": "standard" if require_intact_chain else "integrity",
    }


def build_integrity_report(case_id: str) -> dict:
    """Forensic report that documents custody chain state even when broken."""
    return build_json_report(case_id, require_intact_chain=False)


def build_html_report(case_id: str, *, require_intact_chain: bool = True) -> str:
    report = build_json_report(case_id, require_intact_chain=require_intact_chain)
    case = report["case"]
    rows = "".join(
        f"<tr><td>{escape(str(ev['filename']))}</td><td><code>{escape(str(ev['sha256'][:16]))}…</code></td>"
        f"<td><code>{escape(str((ev.get('md5') or '—')[:16]))}…</code></td><td>{int(ev['size_bytes'])}</td></tr>"
        for ev in report["evidence"]
    )
    recovery_rows = "".join(
        f"<tr><td><code>{escape(str(item['job_id'][:12]))}…</code></td><td>{escape(str(item['status']))}</td>"
        f"<td>{escape(str(item['vendor'] or '—'))}</td><td>{escape(str(item['adapter'] or '—'))}</td>"
        f"<td>{int(item['segment_count'])}</td></tr>"
        for item in report["recovery_summary"]
    )
    custody_rows = "".join(
        f"<tr><td>{escape(str(event['created_at']))}</td><td>{escape(str(event['action']))}</td>"
        f"<td>{escape(str(event['actor']))}</td><td>{escape(str(event.get('detail') or ''))}</td></tr>"
        for event in report["custody_events"][:50]
    )
    chain_ok = report["custody_chain_valid"]["ok"]
    broken_row = report["custody_chain_valid"].get("first_broken_row_id")
    chain_detail = (
        "VALID"
        if chain_ok
        else f"BROKEN at custody row {broken_row}"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Forensic Report — {escape(str(case['title']))}</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;margin:2rem;background:#0a0e1a;color:#eef1f8}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}} th,td{{border:1px solid #2e3a5c;padding:8px;font-size:13px}}
th{{background:#161d30}} code{{font-family:monospace;font-size:12px}}
.ok{{color:#3ba676}} .bad{{color:#d6584f}}
</style></head><body>
<h1>Forensic case report</h1>
<p><strong>{escape(str(case['title']))}</strong> · Examiner: {escape(str(case['examiner']))}</p>
<p>Custody chain: <span class="{'ok' if chain_ok else 'bad'}">{escape(chain_detail)}</span></p>
<p>Version: {escape(str(report['app_version']))}</p>
<h2>Evidence</h2><table><tr><th>File</th><th>SHA-256</th><th>MD5</th><th>Bytes</th></tr>{rows}</table>
<h2>Recovery</h2><table><tr><th>Job</th><th>Status</th><th>Vendor</th><th>Adapter</th><th>Segments</th></tr>{recovery_rows}</table>
<h2>Custody ledger</h2><table><tr><th>Time</th><th>Action</th><th>Actor</th><th>Detail</th></tr>{custody_rows}</table>
<p>{escape(str(report['methodology']))}</p>
</body></html>"""


def build_integrity_html_report(case_id: str) -> str:
    return build_html_report(case_id, require_intact_chain=False)


def build_pdf_report(case_id: str, *, require_intact_chain: bool = True) -> tuple[bytes, str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    report = build_json_report(case_id, require_intact_chain=require_intact_chain)
    case = report["case"]
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

    line("Forensic Workstation — Case Report", "Helvetica-Bold", 14)
    line(f"Case: {case['title']}")
    line(f"Examiner: {case['examiner']}")
    line(f"Generated: {report['generated_at']}")
    line(f"Build: {APP_VERSION}")
    chain_ok = report["custody_chain_valid"]["ok"]
    chain_label = "VALID" if chain_ok else f"BROKEN row {report['custody_chain_valid'].get('first_broken_row_id')}"
    line(f"Custody chain: {chain_label}")
    line(f"Segments recovered: {report['total_segments_recovered']}")
    for ev in report["evidence"]:
        line(f"  {ev['filename']} · SHA-256 {ev['sha256'][:32]}…")
    pdf.save()
    raw = buffer.getvalue()
    signed, fingerprint = sign_pdf_bytes(raw)
    report_id = uuid.uuid4().hex
    output_path = REPORTS_DIR / f"{case_id}_{report_id}.pdf"
    output_path.write_bytes(signed)
    import hashlib

    sha256 = hashlib.sha256(signed).hexdigest()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO reports (id, case_id, generated_at, output_path, output_sha256, pades_certificate_fingerprint)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (report_id, case_id, report["generated_at"], str(output_path), sha256, fingerprint),
        )
        append_custody(
            conn,
            actor="Pramaan Engine",
            action="signed_report_generated",
            target_type="case",
            target_id=case_id,
        )
    return signed, fingerprint


def build_integrity_pdf_report(case_id: str) -> tuple[bytes, str]:
    return build_pdf_report(case_id, require_intact_chain=False)


def _case_legacy_shape(case: dict) -> dict:
    return {
        "id": case["id"],
        "title": case["name"],
        "examiner": case["examiner_name"],
        "reference": case.get("notes"),
        "status": "open",
        "created_at": case["created_at"],
        "updated_at": case["created_at"],
    }


def _device_report_row(device: dict) -> dict:
    path = Path(device["image_path"])
    return {
        "filename": path.name,
        "sha256": device["image_sha256"],
        "md5": device["image_md5"],
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _custody_legacy(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "case_id": entry["target_id"],
        "actor": entry["actor"],
        "action": entry["action"],
        "detail": entry.get("evidence_digest") or entry.get("target_type"),
        "created_at": entry["timestamp_utc"],
    }
