# -*- coding: utf-8 -*-
"""查重：这批 1530 条「新增」里，有多少其实是老素材的变体（换编码/改时长/重传）。

手段：对 6 帧印相做 aHash+dHash（aHash 看整体构图，dHash 看画面梯度），
在同为 1200x840 的拼图上比对，汉明距离小 => 同一条素材的不同版本。

    python dupcheck.py --cur <sheet.csv> --hist <sheet_dir> --out dup_20261123.json
"""
import argparse, csv, json
from pathlib import Path

import numpy as np
from PIL import Image

CUR_CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
HIST_DIR = r"E:\video-download\analysis\assets\sheets_20261116"
LEDGER = r"E:\video-download\analysis\out\master_ledger.csv"


def hashes(p):
    with Image.open(p) as im:
        g = im.convert("L").resize((17, 16), Image.LANCZOS)
        a = np.asarray(g, dtype=np.int16)
    d = (a[:, 1:] > a[:, :-1]).flatten()          # dHash 256 bit
    small = np.asarray(Image.open(p).convert("L").resize((16, 16), Image.LANCZOS))
    h = (small > small.mean()).flatten()           # aHash 256 bit
    return d, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--th", type=int, default=18, help="dHash 汉明距离阈值(256bit)")
    ap.add_argument("--th-a", type=int, default=18, help="aHash 阈值(256bit)")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(CUR_CSV, encoding="utf-8-sig")))
    print(f"本期新增 {len(rows)} 条")

    cur = []
    for r in rows:
        p = Path(r["sheet"])
        if p.exists():
            d, h = hashes(p)
            cur.append((r, d, h))

    # ---- 1) 批内重复 ----
    D = np.array([c[1] for c in cur], dtype=np.uint8)
    H = np.array([c[2] for c in cur], dtype=np.uint8)
    same = []
    n = len(cur)
    for i in range(n):
        dd = np.count_nonzero(D[i] != D[i:], axis=1)
        hh = np.count_nonzero(H[i] != H[i:], axis=1)
        idx = np.where((dd <= a.th) & (hh <= a.th_a))[0]
        for j in idx:
            if i + j == i:
                continue
            same.append((i, i + int(j)))
    pairs = {(min(i, j), max(i, j)) for i, j in same}
    print(f"批内疑似重复对: {len(pairs)}")

    # 连通分量
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    dup_groups = [g for g in groups.values() if len(g) > 1]
    print(f"批内重复组: {len(dup_groups)} 组，涉及 {sum(len(g) for g in dup_groups)} 条"
          f"（可省 {sum(len(g) - 1 for g in dup_groups)} 条转写）")

    # ---- 2) 和历史期（11-16 印相 538 张）比对 ----
    hist = []
    for p in sorted(Path(HIST_DIR).glob("*.jpg")):
        d, h = hashes(p)
        hist.append((p.stem, d, h))
    print(f"历史印相 {len(hist)} 张（11-16 期）")
    HD = np.array([x[1] for x in hist], dtype=np.uint8)
    HH = np.array([x[2] for x in hist], dtype=np.uint8)
    hit = 0
    hit_rows = []
    for r, d, h in cur:
        dd = np.count_nonzero(HD != d, axis=1)
        hh = np.count_nonzero(HH != h, axis=1)
        m = (dd <= a.th) & (hh <= a.th_a)
        if m.any():
            hit += 1
            hit_rows.append((r["file"], hist[int(np.argmax(m))][0], int(dd[np.argmax(m)])))
    print(f"与 11-16 期疑似同素材: {hit} 条（{hit / n:.1%}）")
    for x in hit_rows[:10]:
        print("   ", x[0], "≈", x[1], "dist", x[2])

    # ---- 3) 和台账按文件 stem / 时长找同源 ----
    led = list(csv.DictReader(open(LEDGER, encoding="utf-8-sig")))
    hist_stems = {}
    for x in led:
        hist_stems.setdefault(x["stem"], []).append(x)
    cur_stems = {r["stem"] for r in rows}
    print(f"\n台账 {len(led)} 行 / {len(hist_stems)} 个 stem；本期 {len(cur_stems)} 个 stem")
    print(f"本期 stem 在台账里已出现的: {len(cur_stems & set(hist_stems))}")

    out = dict(total=n, dup_groups=len(dup_groups),
               dup_rows=sum(len(g) for g in dup_groups),
               savings=sum(len(g) - 1 for g in dup_groups),
               hist_hits=hit,
               hist_hit_rows=[x[0] for x in hit_rows])
    Path(r"E:\video-download\analysis\data_20261123\dup_20261123.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n估算可省转写:", out["dup_groups"] and out["savings"], "+ 与上期重复", hit)


if __name__ == "__main__":
    main()
