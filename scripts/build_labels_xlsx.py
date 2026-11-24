# -*- coding: utf-8 -*-
"""把 1530 条新增的视觉打标结果落成拆解表（4 页签 + 印相缩略图）。

    python build_labels_xlsx.py --wl data_20261123\wl_20261123.json \
        --labels data_20261123\labels --csv out\weekly_20261123_新增.csv \
        --out out\2026-11-23_竞品素材拆解表.xlsx

口径对齐 2026-11-16 那版：序号/产品/形态/人物/场景/动作/语言/钩子/卖点/CTA/露出/规格/
画面文案/中文拆解/置信/印相 + 文案库 + 汇总统计 + 产品画像。
"""
import argparse, json, math, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=10)
LOW_FILL = PatternFill("solid", fgColor="FCE4D6")

COLS = [
    ("序号", 6), ("产品", 12), ("时长s", 6), ("形态", 15), ("人物", 8), ("场景", 15),
    ("动作", 10), ("语言", 9), ("钩子", 15), ("卖点", 10), ("CTA", 13), ("露出", 9),
    ("规格", 11), ("画面文案（原文）", 30), ("中文拆解", 30), ("置信", 5), ("印相", 26),
]
KEYS = ["no", "product", "dur", "fmt", "pop", "scene", "act", "lang", "hook",
        "selling", "cta", "prod", "grade", "text", "summary", "conf"]


def wlen(s):
    s = str(s or "")
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def thumb(src, dst, width=360, quality=55):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst
    with Image.open(src) as im:
        h = int(im.height * width / im.width)
        im.convert("RGB").resize((width, h), Image.LANCZOS).save(dst, "JPEG", quality=quality, optimize=True)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wl", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--thumbs", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    a = ap.parse_args()

    wl = json.loads(Path(a.wl).read_text(encoding="utf-8"))["items"]
    by_idx = {it["idx"]: it for it in wl}

    lab = {}
    files = sorted(Path(a.labels).glob("labels_b*.json"))
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8-sig"))
        for r in d.get("labels", []):
            lab[int(r["idx"])] = r
    print(f"worklist {len(wl)} 条 | 打标文件 {len(files)} 个 | 已打标 {len(lab)} 条")
    missing = [i for i in by_idx if i not in lab]
    if missing:
        print(f"⚠ 缺 {len(missing)} 条：{missing[:12]}{'...' if len(missing) > 12 else ''}")

    thumbs = Path(a.thumbs) if a.thumbs else Path(a.labels).parent / "thumbs"

    rows = []
    for idx in sorted(by_idx):
        it = by_idx[idx]
        r = lab.get(idx, {})
        rows.append({
            "no": idx + 1, "product": it["product"], "dur": it["duration"],
            "fmt": r.get("fmt", ""), "pop": r.get("pop", ""), "scene": r.get("scene", ""),
            "act": r.get("act", ""), "lang": r.get("lang", ""), "hook": r.get("hook", ""),
            "selling": r.get("selling", ""), "cta": r.get("cta", ""), "prod": r.get("prod", ""),
            "grade": r.get("grade", ""), "text": r.get("text", ""),
            "summary": r.get("summary", ""), "conf": str(r.get("conf", "")),
            "sheet": it["sheet"], "file": it["file"],
        })

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "1_素材总表"
    ws.append([c for c, _ in COLS])
    for i, (name, w) in enumerate(COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        c = ws.cell(row=1, column=i)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    IMG_H = 82  # px
    ROW_H = IMG_H / 1.333 + 2
    NAMES = [c for c, _ in COLS]
    wrap_idx = {NAMES.index(x) for x in ("场景", "画面文案（原文）", "中文拆解")}
    conf_col = NAMES.index("置信") + 1
    for r in rows:
        vals = [r[k] for k in KEYS] + [""]
        ws.append(vals)
        row = ws.max_row
        lines = 1
        for ci, c in enumerate(ws[row], start=1):
            c.font = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=(ci - 1) in wrap_idx)
            if (ci - 1) in wrap_idx:
                lines = max(lines, math.ceil(wlen(c.value) / max(COLS[ci - 1][1] - 1, 4)))
        ws.row_dimensions[row].height = max(ROW_H, min(13.5 * lines + 3, 120))
        if r["conf"] == "0.5":
            ws.cell(row=row, column=conf_col).fill = LOW_FILL
        # 印相
        src = Path(r["sheet"])
        if src.exists():
            t = thumb(src, thumbs / (src.stem + ".jpg"))
            img = XLImage(str(t))
            img.height = IMG_H
            img.width = int(IMG_H * 1200 / 840)
            ws.add_image(img, f"Q{row}")
    ws.freeze_panes = "A2"

    # 2_文案库
    groups = defaultdict(list)
    for r in rows:
        t = (r["text"] or "").strip()
        if t:
            groups[t].append(r)
    ws2 = wb.create_sheet("2_文案库")
    head2 = ["原文", "语言", "卖点", "形态", "次数", "代表产品", "代表拆解"]
    ws2.append(head2)
    for i, n in enumerate(head2, 1):
        c = ws2.cell(row=1, column=i)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for t, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        ws2.append([t, g[0]["lang"], g[0]["selling"], g[0]["fmt"], len(g),
                    "、".join(sorted({x["product"] for x in g})), g[0]["summary"]])
    for i, w in enumerate([46, 9, 10, 14, 6, 16, 30], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, max_col=7):
        for c in row:
            c.font = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=c.column in (1, 7))

    # 3_汇总统计
    ws3 = wb.create_sheet("3_汇总统计")
    n = len(rows)
    ws3.append([f"{a.title or Path(a.out).stem}｜素材 {n} 条｜"
                f"低置信 {sum(1 for r in rows if r['conf'] == '0.5')} 条"
                f"（{sum(1 for r in rows if r['conf'] == '0.5') / max(n, 1):.0%}）"])
    ws3.cell(row=1, column=1).font = Font(bold=True, size=11)
    ws3.append([])
    for label, key in [("形态 fmt", "fmt"), ("人物 pop", "pop"), ("钩子 hook", "hook"),
                       ("卖点 selling", "selling"), ("CTA", "cta"), ("露出 prod", "prod"),
                       ("规格 grade", "grade"), ("语言 lang", "lang")]:
        ws3.append([label, "条数", "占比"])
        for c in range(1, 4):
            cell = ws3.cell(row=ws3.max_row, column=c)
            cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        for k, v in Counter(r[key] or "(空)" for r in rows).most_common():
            ws3.append([k, v, f"{v/n:.1%}"])
        ws3.append([])
    for i, w in enumerate([22, 8, 9], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # 4_产品画像
    ws4 = wb.create_sheet("4_产品画像")
    head4 = ["产品", "素材数", "时长中位", "主力形态", "主力钩子", "主力卖点", "主力CTA", "无CTA%", "低置信%"]
    ws4.append(head4)
    for i in range(1, len(head4) + 1):
        c = ws4.cell(row=1, column=i)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    byp = defaultdict(list)
    for r in rows:
        byp[r["product"]].append(r)
    for p, g in sorted(byp.items(), key=lambda kv: -len(kv[1])):
        dur = sorted(x["dur"] for x in g)
        ws4.append([p, len(g), dur[len(dur) // 2],
                    Counter(x["fmt"] for x in g).most_common(1)[0][0],
                    Counter(x["hook"] for x in g).most_common(1)[0][0],
                    Counter(x["selling"] for x in g).most_common(1)[0][0],
                    Counter(x["cta"] for x in g).most_common(1)[0][0],
                    f"{sum(1 for x in g if x['cta'] == '无明确CTA') / len(g):.0%}",
                    f"{sum(1 for x in g if x['conf'] == '0.5') / len(g):.0%}"])
    for i, w in enumerate([14, 8, 8, 15, 15, 10, 13, 8, 9], 1):
        ws4.column_dimensions[get_column_letter(i)].width = w
    for row in ws4.iter_rows(min_row=2, max_row=ws4.max_row, max_col=9):
        for c in row:
            c.font = Font(size=9)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(a.out)
    print("saved", a.out, f"({Path(a.out).stat().st_size/1048576:.1f} MB)")


if __name__ == "__main__":
    main()
