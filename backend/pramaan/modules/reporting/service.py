from __future__ import annotations

from datetime import datetime, timezone

from pramaan.core import cases as case_store
from pramaan.modules.custody.hash_chain import verify_chain


def build_json_report(case_id: str) -> dict:
    case = case_store.get_case(case_id)
    if not case:
        raise ValueError("Case not found")
    custody = case_store.list_custody(case_id, limit=500)
    chain = verify_chain(sorted(custody, key=lambda e: e["id"]), case_id)
    return {
        "case": case,
        "evidence_count": len(case_store.list_evidence(case_id)),
        "evidence": case_store.list_evidence(case_id),
        "recovery_jobs": case_store.list_jobs_for_case(case_id),
        "custody_events": custody,
        "custody_chain_valid": chain,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Pramaan",
    }


def build_html_report(case_id: str) -> str:
    report = build_json_report(case_id)
    case = report["case"]
    rows = ""
    for ev in report["evidence"]:
        rows += f"<tr><td>{ev['filename']}</td><td><code>{ev['sha256'][:16]}…</code></td><td>{ev['size_bytes']}</td></tr>"
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
<h2>Evidence</h2><table><tr><th>File</th><th>SHA-256</th><th>Bytes</th></tr>{rows}</table>
<h2>Custody ledger</h2><table><tr><th>Time</th><th>Action</th><th>Actor</th><th>Detail</th></tr>{custody_rows}</table>
<p class="meta">Generated {report['generated_at']} by Pramaan</p>
</body></html>"""
