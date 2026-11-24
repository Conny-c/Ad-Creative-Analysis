# -*- coding: utf-8 -*-
"""生成「可上传的结论输出案例」：小体积、能说明交付物长什么样。

    python make_samples.py

产物（案例输出/）：
  - 2026-11-23_竞品素材拆解表_前25条.xlsx   带印相缩略图的样例
  - 2026-11-23_口播转录表_前25条.xlsx        带口播原文/译文/AI判定的样例
  - 2026-11-23_竞品素材拆解表_全量.csv       1530 行全量数据（无图，便于 diff）
  - 2026-11-23_口播转录表_全量.csv           1530 行全量数据
  - 印相样例_01.jpg / 02 / 03                6 帧拼图长什么样
  - 小结_拆解.md / 小结_口播.md               本期结论页
"""
import csv, shutil
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path(r"E:\video-download\analysis\out")
D = Path(r"E:\video-download\analysis\data_20261123")
DEST = Path(r"E:\video-download\案例输出")
HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
IMG_H = 82


def slice_xlsx(src, dst, n=25, thumbs=None, csv_path=None):
    """取前 n 行；若给了 thumbs + csv_path，就在最右列插一列印相缩略图。"""
    # 序号 -> 缩略图
    seq2thumb = {}
    if thumbs and csv_path:
        rows_csv = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
        for i, r in enumerate(rows_csv, 1):
            p = thumbs / (Path(r["stem"]).stem + ".jpg")
            if p.exists():
                seq2thumb[i] = p

    wb = openpyxl.load_workbook(src, read_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = list(next(it))
    if seq2thumb or thumbs:
        head = head + ["印相（缩略图）"]
    rows = []
    for r in it:
        if r[0] is None:
            continue
        rows.append(r)
        if len(rows) >= n:
            break

    nb = openpyxl.Workbook()
    ns = nb.active
    ns.title = ws.title
    ns.append(head)
    for c in range(1, len(head) + 1):
        cell = ns.cell(row=1, column=c)
        cell.fill, cell.font = HEAD_FILL, Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ns.column_dimensions[get_column_letter(c)].width = 26 if c == len(head) else 12
    for r in rows:
        ns.append(list(r) + [""])
        ns.row_dimensions[ns.max_row].height = IMG_H / 1.333 + 2
    for row in ns.iter_rows(min_row=2, max_row=ns.max_row, max_col=len(head)):
        for c in row:
            c.font = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=False)
    ns.freeze_panes = "A2"

    col = get_column_letter(len(head))
    for i, r in enumerate(rows, start=2):
        p = seq2thumb.get(int(r[0]))
        if p:
            img = XLImage(str(p))
            img.height = IMG_H
            img.width = int(IMG_H * 1200 / 840)
            ns.add_image(img, f"{col}{i}")

    nb.save(dst)
    print(f"  {dst.name}  {len(rows)} 行  {dst.stat().st_size/1024:.0f} KB")
    return head, rows


def dump_csv(src, dst):
    wb = openpyxl.load_workbook(src, read_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = list(next(it))
    n = 0
    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in it:
            if r[0] is None:
                continue
            w.writerow(["" if v is None else v for v in r])
            n += 1
    print(f"  {dst.name}  {n} 行  {dst.stat().st_size/1024:.0f} KB")


def main():
    DEST.mkdir(exist_ok=True)
    print("生成样例：")
    thumbs = D / "thumbs"
    csv23 = OUT / "weekly_20261123_新增.csv"
    slice_xlsx(OUT / "2026-11-23_竞品素材拆解表.xlsx", DEST / "2026-11-23_竞品素材拆解表_前25条.xlsx",
               thumbs=thumbs, csv_path=str(csv23))
    slice_xlsx(OUT / "2026-11-23_口播转录表.xlsx", DEST / "2026-11-23_口播转录表_前25条.xlsx",
               thumbs=thumbs, csv_path=str(csv23))
    dump_csv(OUT / "2026-11-23_竞品素材拆解表.xlsx", DEST / "2026-11-23_竞品素材拆解表_全量.csv")
    dump_csv(OUT / "2026-11-23_口播转录表.xlsx", DEST / "2026-11-23_口播转录表_全量.csv")

    picks = sorted((D / "thumbs").glob("*.jpg"))[:3]
    for i, p in enumerate(picks, 1):
        shutil.copy2(p, DEST / f"印相样例_{i:02d}.jpg")
    print(f"  印相样例 ×{len(picks)}")

    for src, name in [(OUT / "2026-11-23_竞品素材拆解小结.md", "小结_拆解.md"),
                      (OUT / "2026-11-23_口播转录小结.md", "小结_口播.md"),
                      (Path(r"E:\video-download\竞品分析流程_对外版.docx"), "流程_对外版.docx")]:
        if src.exists():
            shutil.copy2(src, DEST / name)
            print(f"  {name}")

    # 全量的 CSV 里去掉「印相」列（是本地路径，别人打开没意义）
    for f in DEST.glob("*_全量.csv"):
        rows = list(csv.reader(open(f, encoding="utf-8-sig")))
        if rows and "印相" in rows[0]:
            i = rows[0].index("印相")
            for r in rows:
                if len(r) > i:
                    r.pop(i)
            with open(f, "w", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh).writerows(rows)
            print(f"  {f.name} 去掉印相列")
    print("\n完成 ->", DEST)


if __name__ == "__main__":
    main()
