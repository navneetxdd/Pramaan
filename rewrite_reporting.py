import re

path = "engine/app/services/reporting.py"
with open(path, "r", encoding="utf-8") as f:
    original = f.read()

# We will completely replace build_html_report, build_pdf_report.
# I'll output the new file content and then write it.

new_html_report = '''def build_html_report(case_id: str, *, require_intact_chain: bool = True) -> str:
    report = build_json_report(case_id, require_intact_chain=require_intact_chain)
    case = report["case"]
    devices = list_devices(case_id)
    
    device_rows = ""
    for d in report["evidence"]:
        trace = {}
        for dev in devices:
            if Path(dev["image_path"]).name == d["filename"]:
                raw = dev.get("detection_trace_json")
                if raw:
                    try:
                        trace = json.loads(raw)
                    except Exception:
                        pass
                break
        
        vendor = escape(str(d.get("vendor", "Unknown")))
        model = escape(str(d.get("model_hint", "Unknown")))
        if trace and "hits" in trace and trace["hits"]:
            top = trace["hits"][0]
            vendor = escape(str(top.get("vendor", vendor)))
            adapter = escape(str(top.get("adapter", "Unknown")))
            conf = escape(f"{top.get('confidence', 0):.2f}")
            fs_info = f"{adapter} (Confidence: {conf})"
        else:
            fs_info = "Unknown"
        
        device_rows += f"<tr><td>{vendor}</td><td>{model}</td><td>{fs_info}</td></tr>"

    provenance_rows = ""
    for device in devices:
        drift = float(device.get("drift_offset_seconds") or 0)
        for sequence in list_sequences(device["id"]):
            original_ts = escape(str(sequence.get("recorder_start_ts") or "Clock never calibrated"))
            corrected_ts = escape(str(sequence.get("corrected_start_ts") or "Not calibrated"))
            
            provenance_rows += (
                f"<tr><td><code>{escape(str(d['sha256'][:16]))}…</code><br/><small>MD5: <code>{escape(str(d.get('md5','-')[:16]))}…</code></small></td>"
                f"<td><code>{escape(str(sequence.get('output_sha256', '')[:16]))}…</code></td>"
                f"<td><code>{escape(str(sequence.get('byte_start')))}</code></td>"
                f"<td>{original_ts}<br/><small>Corrected: {corrected_ts}</small></td>"
                f"<td>{escape(str(sequence.get('validation_level') or 'valid'))}</td></tr>"
            )

    extraction_rows = ""
    for item in report["recovery_summary"]:
        # The recovery process ALWAYS byte-copies the raw H.264 NAL units or bin files.
        # Lossless re-encode is handled at export/transcode time, not here.
        method = "Byte-copied (Lossless)" 
        extraction_rows += (
            f"<tr><td>{escape(str(item.get('adapter') or '-'))}</td>"
            f"<td>{method}</td>"
            f"<td><code>{escape(str(item.get('job_id', ''))[:12])}…</code></td></tr>"
        )

    custody_rows = "".join(
        f"<tr><td>{escape(str(event['created_at']))}</td><td>{escape(_custody_action_label(str(event['action'])))}</td>"
        f"<td>{escape(str(event['actor']))}</td><td><code>{escape(str(event.get('this_row_hash') or '')[:12])}…</code></td></tr>"
        for event in report["custody_events"]
    )
    
    lead_rows = "".join(
        f"<tr><td>{escape(str(lead.get('finding_type') or '-'))}</td>"
        f"<td>{escape(str(lead.get('label') or '-'))}</td>"
        f"<td>{int(lead.get('frame_offset_ms') or 0)}</td>"
        f"<td><code>{escape(str(lead.get('finding_id', ''))[:12])}…</code></td></tr>"
        for lead in report.get("investigative_leads", [])
    )

    chain_ok = report["custody_chain_valid"]["ok"]
    broken_row = report["custody_chain_valid"].get("first_broken_row_id")
    chain_detail = "INTACT" if chain_ok else f"BROKEN at custody row {broken_row}"
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Section 63 Certificate - {escape(str(case['title']))}</title>
<style>
body {{ font-family: 'Inter', system-ui, sans-serif; margin: 2rem auto; max-width: 900px; background: #ffffff; color: #0a0a0a; line-height: 1.5; }}
h1 {{ font-size: 1.5rem; text-align: center; margin-bottom: 0.5rem; }}
.subtitle {{ text-align: center; color: #555555; margin-bottom: 2rem; font-size: 0.9rem; }}
h2 {{ font-size: 1.1rem; color: #2563eb; border-bottom: 1px solid #dddddd; padding-bottom: 0.25rem; margin-top: 2rem; margin-bottom: 1rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.85rem; }}
th, td {{ border: 1px solid #dddddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
th {{ background: #f8fafc; font-weight: 600; color: #555555; }}
code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.9em; background: #f8fafc; padding: 0.125rem 0.25rem; border-radius: 2px; color: #0a0a0a; }}
.signature-block {{ margin-top: 4rem; width: 100%; display: flex; justify-content: space-between; }}
.signature-line {{ border-top: 1px solid #0a0a0a; width: 300px; text-align: center; padding-top: 0.5rem; font-size: 0.85rem; color: #555555; margin-top: 4rem; }}
</style>
</head>
<body>
<h1>CERTIFICATE UNDER SECTION 63</h1>
<div class="subtitle">Bharatiya Sakshya Adhiniyam, 2023<br/>Generated on: {escape(str(report['generated_at']))}</div>

<p><strong>Case ID:</strong> <code>{escape(str(case['id']))}</code><br/>
<strong>Case Name:</strong> {escape(str(case['title']))}<br/>
<strong>Custody Chain:</strong> {escape(chain_detail)}</p>

<h2>1. Device Details</h2>
<table>
  <tr><th>Vendor</th><th>Model / Serial</th><th>Filesystem Identified</th></tr>
  {device_rows or '<tr><td colspan="3">No devices recorded.</td></tr>'}
</table>

<h2>2. Evidence Provenance</h2>
<table>
  <tr><th>Original Image Hash</th><th>Derived Recording Hash</th><th>Offset</th><th>Timestamp</th><th>Status</th></tr>
  {provenance_rows or '<tr><td colspan="5">No recovered sequences.</td></tr>'}
</table>

<h2>3. Extraction Method</h2>
<table>
  <tr><th>Parser / Adapter</th><th>Extraction Type</th><th>Job Reference</th></tr>
  {extraction_rows or '<tr><td colspan="3">No extraction jobs.</td></tr>'}
</table>

<h2>4. Chain of Custody Summary</h2>
<p style="font-size: 0.85rem; color: #555555;">This workstation maintains a tamper-evident, hash-chained ledger of all custody events.</p>
<table>
  <tr><th>Time</th><th>Action</th><th>Actor</th><th>Row Hash</th></tr>
  {custody_rows or '<tr><td colspan="4">No custody events.</td></tr>'}
</table>

""" + (f"<h2>5. AI Findings</h2><table><tr><th>Finding Type</th><th>Label</th><th>Offset (ms)</th><th>Finding Hash/ID</th></tr>{lead_rows}</table>" if lead_rows else "") + f"""

<h2>Attestation</h2>
<p style="font-size: 0.85rem;">I hereby certify that the electronic records described above were extracted and processed by the Pramaan Forensic Workstation in the ordinary course of lawful activities. The hashes, extraction methods, and metadata provided herein were automatically computed and verified by the tool. I assume responsibility for the lawful operation of this tool and the handling of the digital evidence as logged in the chain of custody.</p>

<div class="signature-block">
  <div>
    <p><strong>Examiner / Operator:</strong><br/>{escape(str(case['examiner']) or 'Not recorded')}</p>
  </div>
  <div>
    <div class="signature-line">
      Signature of Officer Certifying This Evidence (Section 63)<br/>
      Name &amp; Designation:<br/><br/>
      Date:
    </div>
  </div>
</div>
</body>
</html>"""
'''

new_pdf_report = """def build_pdf_report(case_id: str, *, require_intact_chain: bool = True) -> tuple[bytes, str]:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import hashlib

    # We use xhtml2pdf if available? No, reportlab platypus
    # Actually, we can use PyHanko + reportlab platypus
    
    report = build_json_report(case_id, require_intact_chain=require_intact_chain)
    case = report["case"]
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, alignment=1, spaceAfter=5)
    style_subtitle = ParagraphStyle('SubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1, spaceAfter=20, textColor=colors.HexColor('#555555'))
    style_h2 = ParagraphStyle('H2Style', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, spaceBefore=15, spaceAfter=10, textColor=colors.HexColor('#2563eb'))
    style_normal = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, spaceAfter=5, textColor=colors.HexColor('#0a0a0a'))
    style_muted = ParagraphStyle('MutedStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, spaceAfter=5, textColor=colors.HexColor('#555555'))
    
    elements = []
    
    elements.append(Paragraph("CERTIFICATE UNDER SECTION 63", style_title))
    elements.append(Paragraph(f"Bharatiya Sakshya Adhiniyam, 2023<br/>Generated on: {report['generated_at']}", style_subtitle))
    
    chain_ok = report["custody_chain_valid"]["ok"]
    broken_row = report["custody_chain_valid"].get("first_broken_row_id")
    chain_detail = "INTACT" if chain_ok else f"BROKEN at custody row {broken_row}"
    
    elements.append(Paragraph(f"<b>Case ID:</b> {case['id']}", style_normal))
    elements.append(Paragraph(f"<b>Case Name:</b> {case['title']}", style_normal))
    elements.append(Paragraph(f"<b>Custody Chain:</b> {chain_detail}", style_normal))
    
    # Tables helper
    def make_table(data, colWidths=None):
        t = Table(data, colWidths=colWidths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#555555')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dddddd')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        return t

    # 1. Device Details
    elements.append(Paragraph("1. Device Details", style_h2))
    device_data = [["Vendor", "Model / Serial", "Filesystem Identified"]]
    devices = list_devices(case_id)
    
    for d in report["evidence"]:
        trace = {}
        for dev in devices:
            if Path(dev["image_path"]).name == d["filename"]:
                raw = dev.get("detection_trace_json")
                if raw:
                    try:
                        trace = json.loads(raw)
                    except Exception:
                        pass
                break
        
        vendor = d.get("vendor", "Unknown")
        model = d.get("model_hint", "Unknown")
        if trace and "hits" in trace and trace["hits"]:
            top = trace["hits"][0]
            vendor = top.get("vendor", vendor)
            adapter = top.get("adapter", "Unknown")
            conf = f"{top.get('confidence', 0):.2f}"
            fs_info = f"{adapter} (Conf: {conf})"
        else:
            fs_info = "Unknown"
        device_data.append([str(vendor), str(model), str(fs_info)])
    
    if len(device_data) == 1:
        device_data.append(["No devices recorded.", "", ""])
    elements.append(make_table(device_data, colWidths=[120, 150, 200]))
    
    # 2. Evidence Provenance
    elements.append(Paragraph("2. Evidence Provenance", style_h2))
    prov_data = [["Orig Hash", "Derived Hash", "Offset", "Timestamp", "Status"]]
    for device in devices:
        drift = float(device.get("drift_offset_seconds") or 0)
        for sequence in list_sequences(device["id"]):
            orig_ts = sequence.get("recorder_start_ts") or "Clock never calib."
            corr_ts = sequence.get("corrected_start_ts") or "Not calibrated"
            d_hash = f"{device.get('image_sha256', '')[:12]}..."
            out_hash = f"{sequence.get('output_sha256', '')[:12]}..."
            prov_data.append([
                d_hash,
                out_hash,
                str(sequence.get('byte_start')),
                f"{orig_ts}\\nCorr: {corr_ts}",
                str(sequence.get('validation_level') or 'valid')
            ])
            
    if len(prov_data) == 1:
        prov_data.append(["No recovered sequences.", "", "", "", ""])
    elements.append(make_table(prov_data, colWidths=[90, 90, 60, 180, 50]))
    
    # 3. Extraction Method
    elements.append(Paragraph("3. Extraction Method", style_h2))
    ext_data = [["Parser / Adapter", "Extraction Type", "Job Reference"]]
    for item in report["recovery_summary"]:
        ext_data.append([
            str(item.get('adapter') or '-'),
            "Byte-copied (Lossless)",
            str(item.get('job_id', ''))[:12] + "..."
        ])
    if len(ext_data) == 1:
        ext_data.append(["No extraction jobs.", "", ""])
    elements.append(make_table(ext_data, colWidths=[150, 150, 170]))
    
    # 4. Chain of Custody Summary
    elements.append(Paragraph("4. Chain of Custody Summary", style_h2))
    elements.append(Paragraph("This workstation maintains a tamper-evident, hash-chained ledger of all custody events.", style_muted))
    cust_data = [["Time", "Action", "Actor", "Row Hash"]]
    for event in report["custody_events"][:50]:
        cust_data.append([
            str(event['created_at']),
            _custody_action_label(str(event['action'])),
            str(event['actor']),
            str(event.get('this_row_hash') or '')[:12] + "..."
        ])
    if len(cust_data) == 1:
        cust_data.append(["No custody events.", "", "", ""])
    elements.append(make_table(cust_data, colWidths=[100, 180, 100, 90]))
    
    # 5. AI Findings
    leads = report.get("investigative_leads", [])
    if leads:
        elements.append(Paragraph("5. AI Findings", style_h2))
        ai_data = [["Type", "Label", "Offset (ms)", "Finding ID"]]
        for lead in leads:
            ai_data.append([
                str(lead.get('finding_type') or '-'),
                str(lead.get('label') or '-'),
                str(int(lead.get('frame_offset_ms') or 0)),
                str(lead.get('finding_id', ''))[:12] + "..."
            ])
        elements.append(make_table(ai_data, colWidths=[100, 150, 80, 140]))
        
    # Attestation
    elements.append(Paragraph("Attestation", style_h2))
    elements.append(Paragraph("I hereby certify that the electronic records described above were extracted and processed by the Pramaan Forensic Workstation in the ordinary course of lawful activities. The hashes, extraction methods, and metadata provided herein were automatically computed and verified by the tool. I assume responsibility for the lawful operation of this tool and the handling of the digital evidence as logged in the chain of custody.", style_normal))
    elements.append(Spacer(1, 40))
    
    # Signature block
    sig_data = [[
        Paragraph(f"<b>Examiner / Operator:</b><br/>{case['examiner'] or 'Not recorded'}", style_normal),
        Paragraph("________________________________________________<br/>Signature of Officer Certifying This Evidence (Section 63)<br/>Name & Designation:<br/><br/>Date:", style_muted)
    ]]
    sig_table = Table(sig_data, colWidths=[230, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
    ]))
    elements.append(sig_table)
    
    doc.build(elements)
    
    raw = buffer.getvalue()
    signed, fingerprint = sign_pdf_bytes(raw)
    report_id = uuid.uuid4().hex
    output_path = REPORTS_DIR / f"{case_id}_{report_id}.pdf"
    output_path.write_bytes(signed)
    
    sha256 = hashlib.sha256(signed).hexdigest()
    with get_db() as conn:
        conn.execute(
            '''
            INSERT INTO reports (id, case_id, generated_at, output_path, output_sha256, pades_certificate_fingerprint)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
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
"""

# Now we need to splice these into `reporting.py`
import ast

def extract_body(code):
    lines = code.splitlines(True)
    # find where build_html_report starts
    start1 = None
    end1 = None
    for i, line in enumerate(lines):
        if line.startswith("def build_html_report"):
            start1 = i
        if start1 is not None and i > start1 and line.startswith("def build_integrity_html_report"):
            end1 = i
            break
            
    start2 = None
    end2 = None
    for i, line in enumerate(lines):
        if line.startswith("def build_pdf_report"):
            start2 = i
        if start2 is not None and i > start2 and line.startswith("def build_integrity_pdf_report"):
            end2 = i
            break
            
    return "".join(lines[:start1]) + new_html_report + "\n\n" + "".join(lines[end1:start2]) + new_pdf_report + "\n\n" + "".join(lines[end2:])

new_content = extract_body(original)
with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("reporting.py updated successfully.")
