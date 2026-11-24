# -*- coding: utf-8 -*-
"""把对外版流程文档从 Markdown 转成 Word（含表格/加粗/列表）。

    python md2docx.py 竞品分析流程_对外版.md 竞品分析流程_对外版.docx
"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm


def set_cn_font(run, name="微软雅黑", size=None, bold=None, color=None):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = color


def add_rich(p, text, size=10.5, bold_all=False):
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2])
            set_cn_font(r, size=size, bold=True)
        else:
            r = p.add_run(part)
            set_cn_font(r, size=size, bold=bold_all)


def main(src, dst):
    lines = Path(src).read_text(encoding="utf-8").splitlines()
    doc = Document()
    # 页边距
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2.0)

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(10.5)

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("---") and set(line.strip()) <= {"-"}:
            i += 1
            continue
        if line.startswith("# "):
            p = doc.add_heading(level=0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(8)
            r = p.add_run(line[2:].strip())
            set_cn_font(r, size=22, bold=True, color=RGBColor(0x1F, 0x2B, 0x3D))
        elif line.startswith("## "):
            p = doc.add_heading(level=1)
            p.paragraph_format.space_before = Pt(16)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run(line[3:].strip())
            set_cn_font(r, size=15, bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
        elif line.startswith("### "):
            p = doc.add_heading(level=2)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(line[4:].strip())
            set_cn_font(r, size=12, bold=True, color=RGBColor(0x2E, 0x5C, 0x8A))
        elif line.startswith("|"):
            # 收集整张表
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = []
            for b in block:
                if re.match(r"^\|[\s:\-|]+\|$", b):
                    continue
                cells = [c.strip() for c in b.strip("|").split("|")]
                rows.append(cells)
            if rows:
                ncol = max(len(r) for r in rows)
                t = doc.add_table(rows=0, cols=ncol)
                t.style = "Light Grid Accent 1"
                t.alignment = WD_TABLE_ALIGNMENT.CENTER
                for ri, cells in enumerate(rows):
                    cells = cells + [""] * (ncol - len(cells))
                    row = t.add_row()
                    for ci, cell in enumerate(cells):
                        p = row.cells[ci].paragraphs[0]
                        p.paragraph_format.space_before = Pt(1)
                        p.paragraph_format.space_after = Pt(1)
                        add_rich(p, cell, size=9, bold_all=(ri == 0))
                doc.add_paragraph()
            continue
        elif line.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            add_rich(p, line.lstrip("> ").strip(), size=10)
        elif re.match(r"^\s*[-*]\s+", line):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            add_rich(p, re.sub(r"^\s*[-*]\s+", "", line), size=10.5)
        elif re.match(r"^\s*\d+\.\s+", line):
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_after = Pt(2)
            add_rich(p, re.sub(r"^\s*\d+\.\s+", "", line), size=10.5)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            add_rich(p, line, size=10.5)
        i += 1

    doc.save(dst)
    print("saved", dst, f"{Path(dst).stat().st_size/1024:.0f} KB",
          f"段落 {len(doc.paragraphs)} / 表格 {len(doc.tables)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
