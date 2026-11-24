# -*- coding: utf-8 -*-
"""把「花字+时长相同」的组，按画面是否相同拆开，看组内口播文本到底一不一致。

结论用途：判断「同花字+同时长」能不能当作「同一条口播」去省转写。
"""
import csv, json, re
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def jac(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / max(len(A | B), 1)


def phash(p):
    a = np.asarray(Image.open(p).convert("L").resize((17, 16), Image.LANCZOS), dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()


def cards(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["1_素材总表"]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ix = {x: i for i, x in enumerate(h)}
    out = {}
    for r in it:
        if r[ix["序号"]] is None:
            continue
        out[int(r[ix["序号"]])] = (str(r[ix["画面文案（原文）"]] or "").strip(), float(r[ix["时长s"]] or 0))
    return out


csv16 = list(csv.DictReader(open(r"E:\video-download\analysis\out\weekly_20261116_新增.csv", encoding="utf-8-sig")))
asr = json.loads(Path(r"E:\video-download\analysis\data_20261116\asr.json").read_text(encoding="utf-8"))
c16 = cards(r"E:\video-download\analysis\out\2026-11-16_竞品素材拆解表.xlsx")

rows = []
for i, r in enumerate(csv16, 1):
    key = str(r["product"]) + "|" + str(r["stem"])
    v = asr.get(key) or {}
    card, dur = c16.get(i, ("", 0))
    if not card or card in ("—", "-") or v.get("verdict") != "vo":
        continue
    p = Path(r["sheet"])
    if not p.exists():
        continue
    rows.append(dict(sheet=str(p), card=norm(card), dur=round(dur, 1),
                     text=v.get("text") or "", ph=phash(p)))

g = defaultdict(list)
for x in rows:
    g[(x["card"], x["dur"])].append(x)

same_vis, diff_vis = [], []
for k, v in g.items():
    if len(v) < 2:
        continue
    for a in range(len(v)):
        for b in range(a + 1, len(v)):
            x, y = v[a], v[b]
            d = int(np.count_nonzero(x["ph"] != y["ph"]))
            s = jac(x["text"], y["text"])
            (same_vis if d <= 14 else diff_vis).append(s)


def rep(name, arr):
    if not arr:
        print(f"{name}: 无样本")
        return
    arr = sorted(arr)
    n = len(arr)
    print(f"{name}: {n} 对 | ≥0.95 占 {sum(1 for x in arr if x >= 0.95) / n:.0%} | "
          f"≥0.85 占 {sum(1 for x in arr if x >= 0.85) / n:.0%} | 中位 {arr[n // 2]:.2f}")


print(f"校准样本 {len(rows)} 条（11-16 有花字+有口播）")
rep("画面相同 + 花字时长相同", same_vis)
rep("画面不同 + 花字时长相同", diff_vis)
