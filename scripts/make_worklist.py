# -*- coding: utf-8 -*-
"""把 weekly_<期号>_新增.csv 变成打标 worklist（wl_multi.json，按 label_guide_v2 契约）。

    python make_worklist.py --csv out\weekly_20261123_新增.csv \
        --out wl_20261123.json --batches 12

输出：
    wl_20261123.json           全部条目（idx/file/product/sheet/duration/cuts/region/source）
    wl_20261123_b01.json ...   按批切好，每批给一个子任务用
    wl_20261123.txt            一行一条的人读清单
"""
import argparse, csv, json, math
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--batches", type=int, default=12)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    items = []
    for i, r in enumerate(rows):
        items.append(dict(
            idx=i,
            file=r.get("file", ""),
            product=r.get("product", ""),
            sheet=r.get("sheet", ""),
            duration=round(float(r.get("duration") or 0), 1),
            cuts=r.get("cuts", ""),
            region=r.get("region", ""),
            source=r.get("source", ""),
        ))
    out = Path(a.out)
    out.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8")

    n = a.batches
    size = math.ceil(len(items) / n) if items else 1
    made = []
    for b in range(n):
        part = items[b * size:(b + 1) * size]
        if not part:
            break
        p = out.with_name(f"{out.stem}_b{b + 1:02d}.json")
        p.write_text(json.dumps({"items": part}, ensure_ascii=False, indent=1), encoding="utf-8")
        made.append((p.name, len(part)))
    txt = out.with_suffix(".txt")
    txt.write_text("\n".join(f'{x["idx"]}\t{x["product"]}\t{x["duration"]}s\t{x["file"]}' for x in items),
                   encoding="utf-8")
    print(f"条目 {len(items)} -> {out.name}，切 {len(made)} 批：")
    for name, k in made:
        print(f"  {name}  {k} 条")


if __name__ == "__main__":
    main()
