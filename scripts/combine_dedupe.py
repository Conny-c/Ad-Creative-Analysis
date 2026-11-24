# -*- coding: utf-8 -*-
"""合并两路查重（画面指纹 + 音频指纹），算出真正需要转写的条数。"""
import csv, json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
AUD = r"E:\video-download\analysis\data_20261123\audio_dup.json"

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
n = len(rows)
idx = {r["file"]: i for i, r in enumerate(rows)}
par = list(range(n))


def find(x):
    while par[x] != x:
        par[x] = par[par[x]]
        x = par[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        par[ra] = rb


def dhash(p):
    a = np.asarray(Image.open(p).convert("L").resize((17, 16), Image.LANCZOS), dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()


def ahash(p):
    a = np.asarray(Image.open(p).convert("L").resize((16, 16), Image.LANCZOS), dtype=np.int16)
    return (a > a.mean()).flatten()


print("算画面指纹…", flush=True)
D = []
H = []
for r in rows:
    p = Path(r["sheet"])
    D.append(dhash(p))
    H.append(ahash(p))
D = np.array(D, dtype=np.uint8)
H = np.array(H, dtype=np.uint8)

vis_pairs = 0
for i in range(n):
    dd = np.count_nonzero(D[i] != D[i:], axis=1)
    hh = np.count_nonzero(H[i] != H[i:], axis=1)
    for j in np.where((dd <= 18) & (hh <= 18))[0]:
        if j == 0:
            continue
        union(i, i + int(j))
        vis_pairs += 1

aud = json.loads(Path(AUD).read_text(encoding="utf-8"))
aud_pairs = 0
for g in aud["groups"]:
    base = idx.get(Path(g[0].split("|", 1)[1] + "").name) if False else None
    # groups 里存的是 "product|stem"，用 stem 找回 index（stem 唯一）
    stem2i = {Path(r["stem"]).stem: i for i, r in enumerate(rows)}
    ids = [stem2i[Path(k.split("|", 1)[1]).stem] for k in g if Path(k.split("|", 1)[1]).stem in stem2i]
    for k in ids[1:]:
        union(ids[0], k)
        aud_pairs += 1

groups = defaultdict(list)
for i in range(n):
    groups[find(i)].append(i)
multi = [g for g in groups.values() if len(g) > 1]
savings = sum(len(g) - 1 for g in multi)

print(f"总 {n} 条")
print(f"画面查重命中对 {vis_pairs}")
print(f"音频查重命中对 {aud_pairs}（组 {len(aud['groups'])}）")
print(f"合并后：重复组 {len(multi)}，涉及 {sum(len(g) for g in multi)} 条，"
      f"可省 {savings} 条 -> 需要转写 {n - savings} 条")

by_p = defaultdict(lambda: [0, 0])
for i, r in enumerate(rows):
    by_p[r["product"]][0] += 1
    if len(groups[find(i)]) == 1:
        by_p[r["product"]][1] += 1
print("\n按产品（原条数 -> 去重后条数）：")
for p, (a, b) in sorted(by_p.items(), key=lambda kv: -kv[1][0])[:12]:
    print(f"  {p:<14} {a:>4} -> {b:>4}")
