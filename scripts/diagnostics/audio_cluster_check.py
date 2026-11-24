# -*- coding: utf-8 -*-
"""检查音频聚类是否靠谱：组内「画面文案」是否一致。

如果一组里花字彼此不同，很可能只是同一首 BGM，口播其实不一样 -> 不该合并。
"""
import csv, json, re
from collections import defaultdict
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image

CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
AUD = r"E:\video-download\analysis\data_20261123\audio_dup.json"


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


wb = openpyxl.load_workbook(r"E:\video-download\analysis\out\2026-11-23_竞品素材拆解表.xlsx", read_only=True)
ws = wb["1_素材总表"]
it = ws.iter_rows(values_only=True)
h = list(next(it))
ix = {x: i for i, x in enumerate(h)}
card = {int(r[ix["序号"]]) - 1: str(r[ix["画面文案（原文）"]] or "").strip() for r in it if r[ix["序号"]]}

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
stem2i = {Path(r["stem"]).stem: i for i, r in enumerate(rows)}
aud = json.loads(Path(AUD).read_text(encoding="utf-8"))

same_card = diff_card = 0
mixed_groups = []
for g in aud["groups"]:
    ids = [stem2i[Path(k.split("|", 1)[1]).stem] for k in g if Path(k.split("|", 1)[1]).stem in stem2i]
    cards = {norm(card.get(i, "")) for i in ids if card.get(i)}
    if len(cards) <= 1:
        same_card += 1
    else:
        diff_card += 1
        mixed_groups.append((len(ids), rows[ids[0]]["product"], sorted(cards)[:3]))

print(f"音频重复组 {len(aud['groups'])} 个：花字完全一致 {same_card} 组，花字不同 {diff_card} 组")
for n, p, cs in sorted(mixed_groups, key=lambda x: -x[0])[:8]:
    print(f"  {n} 条 | {p} | 花字: {[c[:36] for c in cs]}")
