from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO

from pramaan.core import cases as case_store
from pramaan.modules.custody.hash_chain import verify_chain


def _recovery_summary(case_id: str) -> list[dict]:
    summary: list[dict] = []
    for job in case_store.list_jobs_for_case(case_id):
        segments = case_store.list_segments(job["id"])
        stats = {}
        if job.get("stats_json"):
            try:
                stats = json.loads(job["stats_json"])
            except json.JSONDecodeError:
                stats = {}
        summary.append(
            {
                "job_id": job["id"],
                "status": job["status"],
                "vendor": job.get("vendor"),
                "adapter": job.get("adapter"),
                "segment_count": len(segments),
                "stats": stats,
            }
        )
    return summary


def build_json_report(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise ValueError("Case not found")
    custody = case_store.list_custody(case_id, limit=500)
    chain = verify_chain(sorted(custody, key=lambda e: e["id"]), case_id)
    recovery = _recovery_summary(case_id)
    return {
        "case": case,
        "evidence_count": len(case_store.list_evidence(case_id)),
        "evidence": case_store.list_evidence(case_id),
        "recovery_jobs": case_store.list_jobs_for_case(case_id),
        "recovery_summary": recovery,
        "total_segments_recovered": sum(item["segment_count"] for item in recovery),
        "custody_events": custody,
        "custody_chain_valid": chain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Pramaan",
        "methodology": "Dual-signature DHAV validation; HKVI block index; H.264 NAL fallback (MDPI 2025)",
    }


def build_html_report(case_id: str) -> str:
    report = build_json_report(case_id)
    case = report["case"]
    rows = ""
    for ev in report["evidence"]:
        rows += f"<tr><td>{ev['filename']}</td><td><code>{ev['sha256'][:16]}…</code></td><td>{ev['size_bytes']}</td></tr>"
    recovery_rows = ""
    for item in report["recovery_summary"]:
        recovery_rows += (
            f"<tr><td><code>{item['job_id'][:12]}…</code></td>"
            f"<td>{item['status']}</td><td>{item['vendor'] or '—'}</td>"
            f"<td>{item['adapter'] or '—'}</td><td>{item['segment_count']}</td></tr>"
        )
    custody_rows = ""
    for event in report["custody_events"][:50]:
        custody_rows += (
            f"<tr><td>{event['created_at']}</td><td>{event['action']}</td>"
            f"<td>{event['actor']}</td><td>{event.get('detail') or ''}</td></tr>"
        )
    chain_ok = report["custody_chain_valid"]["ok"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Pramaan Report — {case['title']}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;color:#14161a;background:#f7f8fa}}
h1,h2{{font-weight:600}} table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{border:1px solid #d5d9e0;padding:8px;text-align:left;font-size:14px}}
th{{background:#eef0f3}} code{{font-family:monospace;font-size:12px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px}}
.ok{{background:#d7ebe1;color:#1f6b45}} .bad{{background:#f4d9d6;color:#b42318}}
</style></head><body>
<h1>Forensic case report</h1>
<p><strong>{case['title']}</strong> · Examiner: {case['examiner']} · Reference: {case.get('reference') or '—'}</p>
<p>Custody chain: <span class="badge {'ok' if chain_ok else 'bad'}">{'VALID' if chain_ok else 'BROKEN'}</span></p>
<p>Total segments recovered: {report['total_segments_recovered']}</p>
<h2>Evidence</h2><table><tr><th>File</th><th>SHA-256</th><th>Bytes</th></tr>{rows}</table>
<h2>Recovery jobs</h2><table><tr><th>Job</th><th>Status</th><th>Vendor</th><th>Adapter</th><th>Segments</th></tr>{recovery_rows}</table>
<h2>Custody ledger</h2><table><tr><th>Time</th><th>Action</th><th>Actor</th><th>Detail</th></tr>{custody_rows}</table>
<p class="meta">Generated {report['generated_at']} by Pramaan · {report['methodology']}</p>
</body></html>"""


def build_pdf_report(case_id: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    report = build_json_report(case_id)
    case = report["case"]
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    def line(text: str, font: str = "Helvetica", size: int = 10) -> None:
        nonlocal y
        if y < 2 * cm:
            pdf.showPage()
            y = height - 2 * cm
        pdf.setFont(font, size)
        pdf.drawString(2 * cm, y, text[:110])
        y -= 0.45 * cm

    line("Pramaan — Forensic Case Report", "Helvetica-Bold", 14)
    y -= 0.2 * cm
    line(f"Case: {case['title']}")
    line(f"Examiner: {case['examiner']}")
    line(f"Reference: {case.get('reference') or '—'}")
    line(f"Generated: {report['generated_at']}")
    chain_ok = report["custody_chain_valid"]["ok"]
    line(f"Custody chain: {'VALID' if chain_ok else 'BROKEN'}")
    line(f"Segments recovered: {report['total_segments_recovered']}")
    y -= 0.3 * cm
    line("Evidence", "Helvetica-Bold", 11)
    for ev in report["evidence"]:
        line(f"  {ev['filename']} · SHA-256 {ev['sha256'][:32]}… · {ev['size_bytes']} bytes")
    y -= 0.2 * cm
    line("Recovery jobs", "Helvetica-Bold", 11)
    for item in report["recovery_summary"]:
        line(
            f"  {item['job_id'][:16]}… · {item['status']} · "
            f"{item['vendor'] or '—'} / {item['adapter'] or '—'} · {item['segment_count']} segments"
        )
    y -= 0.2 * cm
    line("Custody events (recent)", "Helvetica-Bold", 11)
    for event in report["custody_events"][:25]:
        line(f"  {event['created_at']} · {event['action']} · {event['actor']}")
    y -= 0.2 * cm
    line(report["methodology"], "Helvetica-Oblique", 8)
    pdf.save()
    return buffer.getvalue()
