#!/usr/bin/env python3
"""Render a plain-markdown handout to a nicely formatted A4 PDF (fpdf2 primitives)."""
import sys, os, re
from fpdf import FPDF
from fpdf.fonts import FontFace
from fpdf.enums import TableBordersLayout

FDIR = os.environ.get("PRAMAAN_PDF_FONT_DIR", r"C:\Windows\Fonts")
ACCENT   = (22, 63, 128)
ACCENT_L = (232, 238, 247)
STRIPE   = (247, 249, 252)
BORDER   = (208, 214, 224)
MUTED    = (96, 102, 112)
RULE     = (214, 219, 228)
CALLOUT_BG = (244, 246, 250)

SUBS = {"\u2192": "->", "\u21d2": "=>", "\u2265": ">=", "\u2264": "<=", "\u00d7": "x",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00b7": " - ", "\u2022": "-", "\u00a0": " ",
        "\ufe0f": "", "\u2011": "-"}


def san(s):
    for k, v in SUBS.items():
        s = s.replace(k, v)
    return s


def deco(s):
    """Drop backticks (fpdf2 markdown doesn't render code spans) but keep the text."""
    return s.replace("`", "")


def parse_blocks(md):
    lines = md.split("\n")
    blocks, i = [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s == "---":
            blocks.append(("hr", None)); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            blocks.append((f"h{len(m.group(1))}", m.group(2).strip())); i += 1; continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                if re.match(r"^[\s:|-]+$", raw):
                    i += 1; continue
                rows.append([c.strip() for c in raw.split("|")]); i += 1
            blocks.append(("table", rows)); continue
        if re.match(r"^>\s?", ln):
            buf = []
            while i < len(lines) and re.match(r"^>\s?", lines[i]):
                buf.append(re.sub(r"^>\s?", "", lines[i])); i += 1
            blocks.append(("callout", " ".join(x.strip() for x in buf if x.strip()))); continue
        if re.match(r"^(\s*)([-*]|\d+\.)\s+", ln):
            items = []
            while i < len(lines) and (re.match(r"^(\s*)([-*]|\d+\.)\s+", lines[i]) or
                                      (lines[i].strip() == "" and i + 1 < len(lines) and re.match(r"^\s+\S", lines[i + 1]))):
                li = lines[i]
                if li.strip() == "":
                    i += 1; continue
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", li)
                items.append((len(mm.group(1)), bool(re.match(r"\d+\.", mm.group(2))), mm.group(2), mm.group(3).strip()))
                i += 1
            blocks.append(("list", items)); continue
        buf = [ln]; i += 1
        while i < len(lines):
            nx = lines[i]
            if not nx.strip() or nx.strip() == "---" or nx.strip().startswith("|") \
               or re.match(r"^#{1,4}\s", nx.strip()) or re.match(r"^>\s?", nx) \
               or re.match(r"^(\s*)([-*]|\d+\.)\s+", nx):
                break
            buf.append(nx); i += 1
        blocks.append(("p", " ".join(x.strip() for x in buf)))
    return blocks


class Doc(FPDF):
    def __init__(self, title):
        super().__init__(format="A4")
        self.title_txt = title
        self.set_auto_page_break(True, margin=15)
        self.set_margins(15, 15, 15)
        try:
            for st, fn in [("", "segoeui.ttf"), ("B", "segoeuib.ttf"), ("I", "segoeuii.ttf"), ("BI", "segoeuiz.ttf")]:
                self.add_font("seg", st, os.path.join(FDIR, fn))
            self.set_font("seg", "", 9.5)
        except (FileNotFoundError, RuntimeError):
            # Segoe UI isn't available off Windows (or PRAMAAN_PDF_FONT_DIR wasn't set) —
            # fall back to a core PDF font so the script still runs, just without Unicode glyphs.
            self.set_font("helvetica", "", 9.5)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*RULE); self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)
        self.set_font("seg", "", 7); self.set_text_color(*MUTED)
        self.cell((self.epw) / 2, 5, self.title_txt, align="L")
        self.cell((self.epw) / 2, 5, f"Page {self.page_no()}", align="R")
        self.set_text_color(0)


def col_widths(pdf, rows):
    """Proportional widths; guarantee the longest single unbreakable word fits."""
    n = len(rows[0])
    pdf.set_font("seg", "", 8.3)
    longword = [0.0] * n   # widest single word in the column (mm) -> hard floor
    typ = [0.0] * n        # typical cell width (mm)
    for r in rows:
        for j in range(n):
            txt = re.sub(r"[*_]", "", (r[j] if j < len(r) else "")).replace("`", "")
            typ[j] += min(pdf.get_string_width(txt), 150)
            for word in re.split(r"[\s/(),]+", txt):
                longword[j] = max(longword[j], pdf.get_string_width(word))
    avail = pdf.epw
    typ = [t / len(rows) for t in typ]
    pad = 4.0  # cell padding both sides
    floor = [min(longword[j] + pad, avail * 0.30) for j in range(n)]
    weight = [max(typ[j] * 1.25, floor[j]) for j in range(n)]
    # scale to available width, but never below the per-column floor
    scale = (avail - sum(floor)) / max(sum(w - f for w, f in zip(weight, floor)), 0.1)
    widths = [floor[j] + max(weight[j] - floor[j], 0) * max(scale, 0) for j in range(n)]
    s = sum(widths)
    widths = [w * avail / s for w in widths]
    return tuple(widths)


def render(md_path, pdf_path, title, subtitle):
    md = san(open(md_path, encoding="utf-8").read())
    md = re.sub(r"\A#\s.*\n", "", md, count=1)
    blocks = parse_blocks(md)
    pdf = Doc(title)
    pdf.add_page()
    pdf.set_fill_color(*ACCENT)
    pdf.rect(pdf.l_margin, pdf.get_y(), 3, 15, style="F")
    pdf.set_fill_color(255, 255, 255)
    pdf.set_x(pdf.l_margin + 6)
    pdf.set_font("seg", "B", 21); pdf.set_text_color(*ACCENT)
    pdf.multi_cell(0, 9.5, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0); pdf.ln(1)
    pdf.set_x(pdf.l_margin + 6)
    pdf.set_font("seg", "", 9); pdf.set_text_color(*MUTED)
    pdf.multi_cell(pdf.epw - 6, 4.6, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0); pdf.ln(4)
    pdf.set_draw_color(*ACCENT); pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(5)

    HEAD = FontFace(emphasis="B", color=(20, 20, 20), fill_color=ACCENT_L)

    for kind, val in blocks:
        if kind == "hr":
            pdf.ln(1); pdf.set_draw_color(*RULE); pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y()); pdf.ln(3)
        elif kind == "h1":
            if pdf.get_y() > pdf.h - 55:
                pdf.add_page()
            pdf.ln(3); pdf.set_font("seg", "B", 15); pdf.set_text_color(*ACCENT)
            pdf.multi_cell(0, 7.5, val, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0)
            pdf.set_draw_color(*ACCENT); pdf.set_line_width(0.4)
            pdf.line(pdf.l_margin, pdf.get_y() + 0.5, pdf.w - pdf.r_margin, pdf.get_y() + 0.5)
            pdf.ln(3.5)
        elif kind == "h2":
            if pdf.get_y() > pdf.h - 42:
                pdf.add_page()
            pdf.ln(2.5); pdf.set_fill_color(*ACCENT)
            pdf.rect(pdf.l_margin, pdf.get_y() + 0.6, 2, 5.4, style="F")
            pdf.set_fill_color(255, 255, 255)
            pdf.set_x(pdf.l_margin + 4)
            pdf.set_font("seg", "B", 12.5); pdf.set_text_color(25, 30, 40)
            pdf.multi_cell(0, 6.5, val, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0); pdf.ln(1.5)
        elif kind == "h3":
            if pdf.get_y() > pdf.h - 32:
                pdf.add_page()
            pdf.ln(2); pdf.set_font("seg", "B", 10.5); pdf.set_text_color(35, 40, 50)
            pdf.multi_cell(0, 5.6, val, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0); pdf.ln(1)
        elif kind == "p":
            pdf.set_font("seg", "", 9.5)
            pdf.multi_cell(0, 5, deco(val), markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.6)
        elif kind == "callout":
            pdf.ln(1)
            pad = 3.2
            inner_w = pdf.epw - 6 - 2 * pad
            txt = deco(val)
            pdf.set_font("seg", "", 9)
            lines = pdf.multi_cell(inner_w, 4.9, txt, markdown=True, dry_run=True, output="LINES")
            h = len(lines) * 4.9 + 2 * pad
            if pdf.get_y() + h > pdf.h - pdf.b_margin:
                pdf.add_page()
            y0 = pdf.get_y()
            pdf.set_fill_color(*CALLOUT_BG)
            pdf.rect(pdf.l_margin, y0, pdf.epw, h, style="F")
            pdf.set_fill_color(*ACCENT)
            pdf.rect(pdf.l_margin, y0, 1.8, h, style="F")
            pdf.set_xy(pdf.l_margin + 6 + pad, y0 + pad)
            pdf.set_text_color(28, 34, 44)
            pdf.multi_cell(inner_w, 4.9, txt, markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0)
            pdf.set_y(y0 + h); pdf.ln(3.5)
        elif kind == "list":
            pdf.set_font("seg", "", 9.5)
            for indent, ordered, marker, text in val:
                lvl = 0 if indent < 2 else 1
                bx = pdf.l_margin + 2 + lvl * 5
                gap = 6.5 if ordered else 4.5
                if pdf.get_y() > pdf.h - 22:
                    pdf.add_page()
                pdf.set_x(bx)
                pdf.cell(gap, 5, "-" if not ordered else marker)
                pdf.set_x(bx + gap + 0.5)
                pdf.multi_cell(0, 5, deco(text), markdown=True, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.6)
        elif kind == "table":
            rows = [[deco(re.sub(r"\*\*", "", c)) for c in r] for r in val]
            fr = col_widths(pdf, rows)
            pdf.ln(1)
            pdf.set_font("seg", "", 8.3)
            pdf.set_draw_color(*BORDER); pdf.set_line_width(0.2)
            pdf.set_fill_color(255, 255, 255)
            with pdf.table(col_widths=fr, first_row_as_headings=True, headings_style=HEAD,
                           borders_layout=TableBordersLayout.HORIZONTAL_LINES,
                           line_height=4.4, padding=(1.6, 2.0, 1.6, 2.0),
                           text_align="LEFT", width=pdf.epw) as table:
                for r in rows:
                    row = table.row()
                    for c in r:
                        row.cell(c)
            pdf.ln(3)

    pdf.output(pdf_path)
    print("wrote", os.path.basename(pdf_path), os.path.getsize(pdf_path) // 1024, "KB,", pdf.page_no(), "pages")


if __name__ == "__main__":
    render(*sys.argv[1:5])
