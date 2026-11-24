# -*- coding: utf-8 -*-
"""合并画面+音频两路查重，输出「代表条清单」和「跳过映射」。

    python make_dedupe_list.py --csv out\weekly_20261123_新增.csv \
        --audio-dup data_20261123\audio_dup.json \
        --out-csv out\weekly_20261123_新增_去重.csv \
        --out-map data_20261123\dedupe_map.json

去重后在 _去重.csv 里每条都是「代表条」；被合并掉的记在 map 里，转写结果直接继承。
"""
import argparse, csv, json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--csv", required=True)
ap.add_argument("--audio-dup", required=True)
ap.add_argument("--out-csv", required=True)
ap.add_argument("--out-map", required=True)
ap.add_argument("--vis-th", type=int, default=18)
a = ap.parse_args()

rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
n = len(rows)
par = list(range(n))


def find(x):
    while par[x] != x:
        par[x] = par[par[x]]
        x = par[x]
    return x


def union(x, y):
    rx, ry = find(x), find(y)
    if rx != ry:
        par[max(rx, ry)] = min(rx, ry)   # 保留靠前的那条做代表


def dhash(p):
    x = np.asarray(Image.open(p).convert("L").resize((17, 16), Image.LANCZOS), dtype=np.int16)
    return (x[:, 1:] > x[:, :-1]).flatten()


def ahash(p):
    x = np.asarray(Image.open(p).convert("L").resize((16, 16), Image.LANCZOS), dtype=np.int16)
    return (x > x.mean()).flatten()


D = np.array([dhash(r["sheet"]) for r in rows], dtype=np.uint8)
H = np.array([ahash(r["sheet"]) for r in rows], dtype=np.uint8)
vis = 0
for i in range(n):
    dd = np.count_nonzero(D[i] != D[i:], axis=1)
    hh = np.count_nonzero(H[i] != H[i:], axis=1)
    for j in np.where((dd <= a.vis_th) & (hh <= a.vis_th))[0]:
        if j:
            union(i, i + int(j))
            vis += 1
print(f"画面查重：{vis} 对命中")

stem2i = {Path(r["stem"]).stem: i for i, r in enumerate(rows)}
aud = json.loads(Path(a.audio_dup).read_text(encoding="utf-8"))
aud_n = 0
for g in aud["groups"]:
    ids = [stem2i[Path(k.split("|", 1)[1]).stem] for k in g if Path(k.split("|", 1)[1]).stem in stem2i]
    for k in ids[1:]:
        union(ids[0], k)
        aud_n += 1
print(f"音频查重：{aud_n} 条并入")

groups = defaultdict(list)
for i in range(n):
    groups[find(i)].append(i)
multi = {k: v for k, v in groups.items() if len(v) > 1}

keep, skip = [], {}
for i in range(n):
    root = find(i)
    if root == i:
        keep.append(i)
    else:
        skip[rows[i]["file"]] = rows[root]["file"]

out_rows = [rows[i] for i in keep]
with open(a.out_csv, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

Path(a.out_map).write_text(json.dumps(
    dict(total=n, keep=len(out_rows), skip=len(skip),
         skip_map=skip, clusters={str(rows[k]["file"]): [rows[i]["file"] for i in v] for k, v in multi.items()}),
    ensure_ascii=False, indent=1), encoding="utf-8")

mins = sum(float(r["duration"]) for r in out_rows) / 60
print(f"\n{ n } 条 -> 代表条 {len(out_rows)}，跳过 {len(skip)}（{len(skip)/n:.1%}）")
print(f"代表条音频 {mins:.0f} 分钟（原 561 分钟）")
print("写出:", a.out_csv, "|", a.out_map)
