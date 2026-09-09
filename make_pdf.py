import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def create_pdf(output_path):
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, spaceAfter=10)
    style_h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, spaceBefore=15, spaceAfter=5)
    style_h3 = ParagraphStyle('H3', parent=styles['Heading3'], fontSize=12, spaceBefore=10, spaceAfter=5)
    style_normal = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, spaceAfter=6, leading=14)
    style_bullet = ParagraphStyle('Bullet', parent=styles['Normal'], fontSize=10, spaceAfter=3, leading=14, leftIndent=20, bulletIndent=10)
    
    elements = []
    
    elements.append(Paragraph("Pramaan Evidence Catalog Feature Context", style_title))
    elements.append(Paragraph("The Evidence Catalog is a centralized module within the Pramaan forensic workstation designed to manage, inspect, and track digital evidence items associated with a case. It serves as the primary hub for examiners to browse acquired media and track their forensic lifecycle.", style_normal))
    
    elements.append(Paragraph("Key Components Implemented", style_h2))
    
    # 1
    elements.append(Paragraph("1. Faceted Filtering & Search (Left Sidebar)", style_h3))
    elements.append(Paragraph("Users can drill down into large evidence sets using multi-dimensional filters:", style_normal))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Categories:</b> Differentiates between raw 'Block Images' (physical acquisitions) and 'Disk Images' (logical acquisitions).", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Status Tracking:</b> Filters items by lifecycle states: 'Verified' (hash matched), 'Awaiting Hash' (verification pending), 'Parsing' (extraction in progress), and 'Failed'.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Text Search:</b> A robust text filter to quickly isolate specific evidence files by name.", style_bullet))
    
    # 2
    elements.append(Paragraph("2. Dual-Mode Catalog Views (Center Pane)", style_h3))
    elements.append(Paragraph("The primary viewing area supports two interchangeable layouts:", style_normal))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Grid View:</b> A visual card-based layout providing quick telemetry: source category icons, file sizes, truncated SHA-256 hashes, and color-coded status badges.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>List View:</b> A dense, tabular data table optimized for bulk analysis, showing complete filenames, exact byte sizes, statuses, and full hash strings.", style_bullet))
    elements.append(Paragraph("Both views support sorting by 'Recent', 'Size', and 'Name'.", style_normal))
    
    # 3
    elements.append(Paragraph("3. Evidence Inspector (Right Sidebar)", style_h3))
    elements.append(Paragraph("When an evidence item is selected from the catalog, this dynamic panel reveals deep forensic metadata:", style_normal))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Item Provenance:</b> Details the acquisition method, format, and physical/logical origin.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Chain of Custody:</b> A filtered ledger showing only the tamper-evident custody events (e.g., acquisition, verification, parsing) specific to the selected item.", style_bullet))
    
    # 4
    elements.append(Paragraph("4. Global Telemetry Strip (Bottom Footer)", style_h3))
    elements.append(Paragraph("A persistent status bar summarizing the case's aggregate metrics:", style_normal))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Storage Bytes:</b> Total disk footprint of all acquired evidence.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Recovered Artifacts:</b> Total number of video segments extracted from the evidence.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Processing Jobs:</b> Live count of active/running forensic tasks.", style_bullet))
    elements.append(Paragraph("<bullet>&bull;</bullet><b>Audit Errors:</b> Count of failed jobs requiring examiner intervention.", style_bullet))
    
    doc.build(elements)

if __name__ == "__main__":
    create_pdf("EVIDENCE.PDF")
