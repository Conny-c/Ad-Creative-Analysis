# -*- coding: utf-8 -*-
"""累积打标台账：把各期拆解表的视觉标签并成一张表（按 md5），下周只打新增。

    python build_label_ledger.py --work analysis --all
"""
import argparse, csv
from pathlib import Path

import openpyxl

COLS = ["期号", "md5", "product", "file", "dur", "fmt", "pop", "scene", "act", "lang",
        "hook", "selling", "cta", "露出", "grade", "text", "summary", "conf"]
MAP = {"形态": "fmt", "人物": "pop", "场景": "scene", "动作": "act", "语言": "lang",
       "钩子": "hook", "卖点": "selling", "CTA": "cta", "露出": "露出", "规格": "grade",
       "画面文案（原文）": "text", "中文拆解": "summary", "置信": "conf", "时长s": "dur"}


def build(work, period, xlsx_path):
    work = Path(work)
    cand = sorted(work.joinpath("out").glob(f"weekly_{period}_新增.csv"))
    if not cand or not Path(xlsx_path).exists():
        print(f"[skip] {period}: 缺 weekly CSV 或拆解表")
        return []
    rows = list(csv.DictReader(open(cand[0], encoding="utf-8-sig")))
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["1_素材总表"]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ix = {x: i for i, x in enumerate(h)}
    out = []
    for r in it:
        if r[ix["序号"]] is None:
            continue
        i = int(r[ix["序号"]]) - 1
        if i >= len(rows):
            continue
        src = rows[i]
        d = dict(期号=period, md5=src.get("md5", ""), product=src["product"], file=src["file"])
        for k, v in MAP.items():
            if k in ix:
                d[v] = ("" if r[ix[k]] is None else str(r[ix[k]]))
        out.append(d)
    print(f"{period}: {len(out)} 条")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=r"E:\video-download\analysis")
    a = ap.parse_args()
    work = Path(a.work)
    out_dir = work / "out"

    # 期号 -> 拆解表文件名（按现有产物约定）
    pairs = []
    for p in sorted(work.glob("data_*")):
        per = p.name.replace("data_", "")
        if not per.isdigit():
            continue
        cand = sorted(out_dir.glob(f"*{per[:4]}-{per[4:6]}-{per[6:]}*拆解表*.xlsx"))
        if cand:
            pairs.append((per, str(cand[0])))
    if not pairs:
        print("没找到拆解表")
        return

    all_rows = []
    for per, path in pairs:
        all_rows += build(work, per, path)
    lp = out_dir / "label_ledger.csv"
    old = []
    if lp.exists():
        old = [r for r in csv.DictReader(open(lp, encoding="utf-8-sig"))]
        keep = {(r["期号"], r["md5"]) for r in all_rows}
        old = [r for r in old if (r["期号"], r["md5"]) not in keep]
    merged = old + all_rows
    with open(lp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in merged:
            w.writerow(r)
    print(f"\n打标台账 {lp.name}: 本次 {len(all_rows)}，历史 {len(old)}，合计 {len(merged)}")


if __name__ == "__main__":
    main()
