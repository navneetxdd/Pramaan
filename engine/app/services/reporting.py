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
    list_included_ai_findings_for_case,
    list_jobs_for_case,
    list_sequences,
)
from engine.app.core.signing import sign_pdf_bytes

_CUSTODY_ACTION_LABELS = {
    "case_created": "Case created",
    "case_exported": "Case exported",
    "case_imported": "Case imported",
    "evidence_acquired": "Evidence acquired",
    "evidence_acquisition_verification_failed": "Evidence verification failed",
    "ai_analytics_completed": "AI analytics completed",
    "ai_analytics_completed_with_warnings": "AI analytics completed (with warnings)",
    "ai_analytics_skipped_unavailable": "AI analytics skipped (unavailable)",
    "cross_camera_correlation_run": "Cross-camera correlation run",
    "cross_camera_still_saved": "Cross-camera still saved as evidence",
    "recovery_started": "Recovery started",
    "recovery_adapter_manually_selected": "Recovery adapter selected manually",
    "recovery_superseded_prior_results": "Recovery re-run, replacing prior results",
    "sequence_artifact_created": "Recovered segment added",
    "recovery_completed": "Recovery completed",
    "recovery_failed": "Recovery failed",
    "signed_report_generated": "Signed report generated",
}


_ACQUISITION_METHOD_LABELS = {
    "operator_oem_image": "Operator OEM image",
    "logical_network": "Logical network acquisition",
    "logical_file_acquisition": "Logical file acquisition",
    "physical_imaging": "Physical imaging",
    "upload": "File upload",
    "synthetic_specimen": "Builder image",
}
_WRITE_BLOCKER_LABELS = {
    "source_opened_read_only": "Source opened read-only (software)",
    "hardware": "Hardware write blocker",
    "none": "None",
}
_CAPABILITY_TIER_LABELS = {
    "validated_parser": "Validated parser (fixture scope)",
    "experimental_parser": "Experimental parser",
    "acquisition_generic_only": "Acquisition and generic only",
    "filesystem_recovery": "Filesystem undelete",
}
_VALIDATION_SCOPE_LABELS = {
    "builder_and_known_fixtures": "Proven on builder and known fixtures only",
    "builder_fixture_only": "Proven on builder fixtures only",
    "signature_match_only": "Signature match only, parser not run for this family",
    "generic_signature_carving_only": "Generic carving only, no vendor-specific parser",
    "annex_b_signature_only": "Generic H.264 signature only, no vendor structure",
    "pytsk3_tier2": "Filesystem undelete via The Sleuth Kit",
}
_ADAPTER_LABELS = {
    "hikvision": "Hikvision HIKBTREE index",
    "dahua_dhav": "Dahua DHAV frame carve",
    "honeywell": "Honeywell index",
    "h264_carve": "H.264 stream carve",
    "generic_tier2": "Generic filesystem / carve",
    "needs_selection": "Adapter not selected",
}

# Structural markers the engine stores in recovered_sequences.validation_level.
# Mirrors DELETED_VALIDATIONS / ALLOCATED_VALIDATIONS / STRUCTURAL_VALIDATIONS in
# src/lib/allocation.ts so the court report and the live app say the same word.
_DELETED_MARKERS = {
    "hikbtree_deleted_entry",
    "honeywell_expired_index",
    "filesystem_deleted_inode",
    "slack_recovered",
    "unreferenced_carve",
    "h264_nal_tail",
}
_ALLOCATED_MARKERS = {
    "hikbtree_indexed",
    "honeywell_index_4",
    "honeywell_format_carve_4",
    "hkvi_block_4",
    "hkvi_block",
}
_STRUCTURAL_MARKERS = {"dual_signature", "dual_signature_4"}


def _label(value: object, table: dict[str, str], fallback: str = "—") -> str:
    text = str(value).strip() if value not in (None, "") else ""
    if not text:
        return fallback
    return table.get(text, text.replace("_", " "))


def _clip_offset(ms: object) -> str:
    """Milliseconds into a recovered clip as m:ss."""
    try:
        total = max(0, int(ms or 0)) // 1000
    except (TypeError, ValueError):
        return "0:00"
    return f"{total // 60}:{total % 60:02d}"


def _allocation_label(sequence: dict) -> str:
    """Human allocation state for one recovered segment, mirroring allocationOf()
    in src/lib/allocation.ts: prefer the engine's own allocation_state, fall back
    to the validation-marker vocabulary, never guess 'allocated'."""
    evidence = sequence.get("validation_evidence") or {}
    raw = evidence.get("allocation_state")
    if isinstance(raw, str):
        value = raw.lower()
        for prefix, text in (
            ("deleted", "Deleted"),
            ("recording", "In-progress recording"),
            ("allocated", "Allocated"),
            ("carve", "Carve (no allocation map)"),
            ("structural", "Structurally complete (no allocation map)"),
        ):
            if value.startswith(prefix):
                return text
    marker = str(sequence.get("validation_level") or "").strip()
    if marker in _DELETED_MARKERS:
        return "Deleted / unreferenced"
    if marker in _STRUCTURAL_MARKERS:
        return "Structurally complete (no allocation map)"
    if marker in _ALLOCATED_MARKERS:
        return "Allocated (live index entry)"
    if marker == "hikbtree_recording":
        return "In-progress recording"
    return marker.replace("_", " ") if marker else "Unclassified"


def _custody_action_label(action: str) -> str:
    """Mirrors src/lib/integrity.ts's custodyActionLabel. This report is read by
    examiners and the court directly, not just the live app; keep both
    humanized."""
    code, _, detail = action.partition(":")
    label = _CUSTODY_ACTION_LABELS.get(code, code.replace("_", " "))
    return f"{label}: {detail}" if detail else label


def _recovery_summary(case_id: str) -> list[dict]:
    """One row per device: the sequences currently in the catalog, plus the
    recovery run that produced them. A device is the unit here — earlier this
    returned a job row *and* a device row per device, which double-counted the
    same sequences in `total_segments_recovered` and in the report table."""
    recovery_jobs: list[dict] = []
    for job in list_jobs_for_case(case_id):
        if job.get("kind") != "recovery":
            continue
        result = job.get("result") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {}
        recovery_jobs.append({**job, "_result": result})

    summary: list[dict] = []
    for device in list_devices(case_id):
        sequences = list_sequences(device["id"])
        device_jobs = [j for j in recovery_jobs if j.get("device_id") == device["id"]]
        last_job = device_jobs[-1] if device_jobs else None
        summary.append(
            {
                "summary_type": "current_sequences",
                "device_id": device["id"],
                "job_id": last_job["id"] if last_job else None,
                "status": last_job["status"] if last_job else "no recovery run",
                "vendor": device.get("declared_brand")
                or (last_job["_result"].get("vendor") if last_job else None),
                "adapter": device.get("detected_engine")
                or (last_job["_result"].get("adapter") if last_job else None),
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
    leads = list_included_ai_findings_for_case(case_id)
    return {
        "case": _case_legacy_shape(case),
        "evidence_count": len(devices),
        "evidence": [_device_report_row(d) for d in devices],
        "recovery_summary": recovery,
        "total_segments_recovered": sum(item["segment_count"] for item in recovery),
        "investigative_leads": [
            {
                "finding_id": lead["id"],
                "device_id": lead.get("device_id"),
                "sequence_id": lead.get("sequence_id"),
                "finding_type": lead.get("finding_type"),
                "label": lead.get("label"),
                "frame_offset_ms": lead.get("frame_offset_ms"),
                "confidence": lead.get("confidence"),
            }
            for lead in leads
        ],
        "custody_events": [_custody_legacy(e) for e in custody],
        "custody_chain_valid": {"ok": chain["intact"], **chain},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "Forensic Workstation",
        "app_version": APP_VERSION,
        # Hikvision data blocks hold raw H.264 Annex-B NAL units behind proprietary
        # picture-index headers, not MPEG-PS. See docs/reference/hikvision_fs.md §5.1.
        "methodology": (
            "Tier 1 DHAV + HIKBTREE index to H.264 NAL extraction, "
            "Tier 2 filesystem undelete and H.264 carve"
        ),
        "report_kind": "standard" if require_intact_chain else "integrity",
    }


def build_integrity_report(case_id: str) -> dict:
    """Forensic report that documents custody chain state even when broken."""
    return build_json_report(case_id, require_intact_chain=False)


def build_html_report(case_id: str, *, require_intact_chain: bool = True) -> str:
    report = build_json_report(case_id, require_intact_chain=require_intact_chain)
    case = report["case"]
    devices = list_devices(case_id)
    logical_only = any((device.get("acquisition_method") == "logical_network") for device in devices)
    from engine.app.services.evidence_provenance import BUILDER_IMAGE_BANNER, detect_acquisition_class

    builder_notices: list[str] = []
    for device in devices:
        path = Path(device["image_path"])
        if not path.exists():
            continue
        acquisition_class = detect_acquisition_class(path)
        if acquisition_class:
            builder_notices.append(f"{path.name}: {acquisition_class['message']}")
    builder_banner = (
        f"<p style='color:#b00020;border:1px solid #b00020;padding:8px;'><strong>{escape(BUILDER_IMAGE_BANNER)}</strong>"
        f"<br/>{escape(' · '.join(builder_notices))}</p>"
        if builder_notices
        else ""
    )
    rows = "".join(
        f"<tr><td>{escape(str(ev['filename']))}</td><td><code>{escape(str(ev['sha256'][:16]))}…</code></td>"
        f"<td><code>{escape(str((ev.get('md5') or '—')[:16]))}…</code></td><td>{int(ev['size_bytes'])}</td>"
        f"<td>{escape(_label(ev.get('acquisition_method'), _ACQUISITION_METHOD_LABELS))}</td>"
        f"<td>{escape(_label(ev.get('write_blocker'), _WRITE_BLOCKER_LABELS))}</td></tr>"
        for ev in report["evidence"]
    )
    logical_banner = (
        "<p><strong>Logical acquisition notice:</strong> One or more devices were acquired over a "
        "read-only network API. Unallocated space and deleted-data recovery are not available for those clips.</p>"
        if logical_only
        else ""
    )
    def _recovery_id(item: dict) -> str:
        ref = item.get("job_id") or item.get("device_id") or ""
        return f"{str(ref)[:12]}…" if ref else "—"

    recovery_rows = "".join(
        f"<tr><td><code>{escape(_recovery_id(item))}</code></td>"
        f"<td>{escape(str(item.get('status') or 'no recovery run').replace('_', ' ').capitalize())}</td>"
        f"<td>{escape(str(item.get('vendor') or '—'))}</td><td>{escape(_label(item.get('adapter'), _ADAPTER_LABELS))}</td>"
        f"<td>{int(item['segment_count'])}</td></tr>"
        for item in report["recovery_summary"]
    )
    custody_rows = "".join(
        f"<tr><td>{escape(str(event['created_at']))}</td><td>{escape(_custody_action_label(str(event['action'])))}</td>"
        f"<td>{escape(str(event['actor']))}</td><td>{escape(str(event.get('detail') or ''))}</td></tr>"
        for event in report["custody_events"][:50]
    )
    lead_rows = "".join(
        f"<tr><td>{escape(str(lead.get('finding_type') or '—').replace('_', ' '))}</td>"
        f"<td>{escape(str(lead.get('label') or '—'))}</td>"
        f"<td>{escape(_clip_offset(lead.get('frame_offset_ms')))}</td>"
        f"<td>{escape((format(lead['confidence'], '.2f') + (' (low)' if lead['confidence'] < 0.6 else '')) if lead.get('confidence') is not None else '—')}</td>"
        f"<td><code>{escape(str(lead.get('finding_id', ''))[:12])}…</code></td></tr>"
        for lead in report.get("investigative_leads", [])
    )
    capability_rows = ""
    timeline_notes: list[str] = []
    provenance_rows = ""
    coverage = "No evidence attached."
    _seen_routes: set[tuple[str, str]] = set()
    for device in devices:
        trace_raw = device.get("detection_trace_json")
        trace: dict = {}
        if trace_raw:
            try:
                trace = json.loads(trace_raw) if isinstance(trace_raw, str) else trace_raw
            except json.JSONDecodeError:
                trace = {}
        coverage = trace.get("coverage_note") or "Identification is marker-based routing, not field validation."
        hits = trace.get("hits") or []
        for hit in hits[:8]:
            route = (str(hit.get("vendor", "")), str(hit.get("adapter", "")))
            if route in _seen_routes:
                continue
            _seen_routes.add(route)
            capability_rows += (
                f"<tr><td>{escape(str(hit.get('vendor', '—')))}</td>"
                f"<td>{escape(_label(hit.get('adapter'), _ADAPTER_LABELS))}</td>"
                f"<td>{escape(_label(hit.get('capability_tier'), _CAPABILITY_TIER_LABELS, 'Generic'))}</td>"
                f"<td>{escape(_label(hit.get('validation_scope'), _VALIDATION_SCOPE_LABELS, 'Routing hint'))}</td></tr>"
            )
        drift = float(device.get("drift_offset_seconds") or 0)
        timeline_notes.append(
            f"Device {escape(device['id'][:12])}… drift {drift:+.1f}s · adapter "
            f"{escape(_label(device.get('detected_engine'), _ADAPTER_LABELS, 'unknown'))}"
        )
        for sequence in list_sequences(device["id"]):
            provenance_rows += (
                f"<tr><td>{escape(str(sequence.get('channel')))}</td>"
                f"<td><code>{escape(str(sequence.get('byte_start')))}</code></td>"
                f"<td><code>{escape(str(sequence.get('byte_end')))}</code></td>"
                f"<td>{escape(_label(sequence.get('parser_name'), _ADAPTER_LABELS, '—'))}</td>"
                f"<td>{escape(_allocation_label(sequence))}</td>"
                f"<td><code>{escape(str(sequence.get('output_sha256', '')[:16]))}…</code></td></tr>"
            )
    chain_ok = report["custody_chain_valid"]["ok"]
    broken_row = report["custody_chain_valid"].get("first_broken_row_id")
    chain_detail = "INTACT" if chain_ok else f"BROKEN at custody row {broken_row}"
    timeline_section = "<br/>".join(timeline_notes) if timeline_notes else "Byte-offset ordering only; no recorder clock recovered."
    adapters_used = sorted({
        _label(item.get("adapter"), _ADAPTER_LABELS)
        for item in report["recovery_summary"]
        if item.get("adapter")
    })
    scope_line = (
        f"Recovery in this case used: {', '.join(adapters_used)}. "
        if adapters_used
        else ""
    ) + "The table below lists every parser the identification scan considered for this evidence."
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Forensic report: {escape(str(case['title']))}</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;margin:2rem;background:#ffffff;color:#111418}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}} th,td{{border:1px solid #d7dbe0;padding:8px;font-size:13px;vertical-align:top}}
th{{background:#f4f6f8;text-align:left}} code{{font-family:monospace;font-size:12px}}
.ok{{color:#0f7b3f}} .bad{{color:#b00020}} h2{{margin-top:2rem}}
.meta{{margin:0.15rem 0;font-size:13px}} .meta b{{display:inline-block;min-width:9rem}}
.signoff{{margin-top:2.5rem;padding-top:1rem;border-top:1px solid #d7dbe0;font-size:13px}}
.signoff .line{{display:inline-block;border-bottom:1px solid #111418;min-width:16rem;margin:0 0.5rem}}
</style></head><body>
<h1>Forensic case report</h1>
<p class="meta"><b>Case</b>{escape(str(case['title']))}</p>
{f'<p class="meta"><b>Reference</b>{escape(str(case["reference"]))}</p>' if case.get('reference') else ''}
<p class="meta"><b>Examiner</b>{escape(str(case['examiner']))}</p>
<p class="meta"><b>Custody chain</b><span class="{'ok' if chain_ok else 'bad'}">{escape(chain_detail)}</span></p>
<p class="meta"><b>Report generated</b>{escape(str(report['generated_at'])[:19].replace('T', ' '))} UTC</p>
<p class="meta"><b>Tool</b>Pramaan {escape(str(report['app_version']))}</p>
{builder_banner}
{logical_banner}
<h2>Evidence</h2><table><tr><th>File</th><th>SHA-256</th><th>MD5</th><th>Bytes</th><th>Acquisition</th><th>Write blocker</th></tr>{rows}</table>
<h2>Capability &amp; validation scope</h2>
<p>{escape(scope_line)}</p>
<p>{escape(coverage)}</p>
<table><tr><th>Vendor</th><th>Adapter</th><th>Tier</th><th>Scope</th></tr>{capability_rows or '<tr><td colspan="4">No identification hits recorded.</td></tr>'}</table>
<h2>Timeline normalization</h2><p>{timeline_section}</p>
<h2>Recovery summary</h2><table><tr><th>Recovery run</th><th>Status</th><th>Vendor</th><th>Adapter</th><th>Segments in catalog</th></tr>{recovery_rows}</table>
<h2>Segment provenance</h2><table><tr><th>Ch</th><th>Byte start</th><th>Byte end</th><th>Parser</th><th>Allocation</th><th>Artifact SHA-256</th></tr>{provenance_rows or '<tr><td colspan="6">No recovered sequences.</td></tr>'}</table>
<h2>Investigative leads (examiner-selected)</h2>
<p>Leads marked INCLUDED by the examiner. These are analytical hints only, not verified evidence.</p>
<table><tr><th>Type</th><th>Label</th><th>Into clip</th><th>Confidence</th><th>Finding ID</th></tr>{lead_rows or '<tr><td colspan="5">No examiner-selected leads.</td></tr>'}</table>
<h2>Custody ledger</h2><table><tr><th>Time</th><th>Action</th><th>Actor</th><th>Detail</th></tr>{custody_rows}</table>
<h2>Methodology</h2><p>{escape(str(report['methodology']))}</p>
<div class="signoff">
<p>The examiner named above certifies that the acquisition, recovery and analysis
recorded here were carried out as described, and that the custody chain is as stated.</p>
<p style="margin-top:1.5rem">Examiner signature <span class="line">&nbsp;</span> Date <span class="line">&nbsp;</span></p>
</div>
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
    chain_label = "INTACT" if chain_ok else f"BROKEN at custody row {report['custody_chain_valid'].get('first_broken_row_id')}"
    line(f"Custody chain: {chain_label}")
    line(f"Segments recovered: {report['total_segments_recovered']}")
    for ev in report["evidence"]:
        line(f"  {ev['filename']} · SHA-256 {ev['sha256'][:32]}…")
    leads = report.get("investigative_leads") or []
    if leads:
        line("Investigative leads (examiner-selected, not verified evidence):", "Helvetica-Bold", 11)
        for lead in leads[:20]:
            label = lead.get("label") or lead.get("finding_type") or "lead"
            line(
                f"  {label} at {_clip_offset(lead.get('frame_offset_ms'))} into clip"
                f" conf={lead.get('confidence', '—')}"
            )
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
    method = device.get("acquisition_method") or "logical_file_acquisition"
    return {
        "filename": path.name,
        "sha256": device["image_sha256"],
        "md5": device["image_md5"],
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "acquisition_method": method,
        "write_blocker": device.get("write_blocker"),
        "source_type": device.get("source_type"),
        "source_identifier": device.get("source_identifier"),
        "logical_only": method == "logical_network",
    }


def _custody_legacy(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "case_id": entry["target_id"],
        "actor": entry["actor"],
        "action": entry["action"],
        # target_type is always "case" for these rows; showing it adds a column
        # of noise. Keep the evidence digest when there is one, else nothing.
        "detail": entry.get("evidence_digest") or "",
        "created_at": entry["timestamp_utc"],
    }
