# -*- coding: utf-8 -*-
"""检查近似复用是否靠谱：列出相似度落在 [0.80,0.90) 的配对。"""
import difflib, json
from pathlib import Path

D = Path(r"E:\video-download\analysis\data_20261116")
index = json.loads((D / "vo_index.json").read_text(encoding="utf-8"))
tr = {}
for f in sorted(D.glob("vo_zh_p*.json")):
    tr.update(json.loads(f.read_text(encoding="utf-8")))
done = [(s, index[s]["text"]) for s in index if s in tr]

pairs = []
for s in index:
    if s in tr:
        continue
    t = index[s]["text"]
    best = max((difflib.SequenceMatcher(None, t[:260], dt[:260]).quick_ratio(), ds)
               for ds, dt in done) if done else (0.0, None)
    if 0.80 <= best[0] < 0.90:
        pairs.append((best[0], s, best[1]))
pairs.sort()
print("0.80~0.90 的复用配对:", len(pairs))
for score, s, ds in pairs[:12]:
    print(f"\n[{score:.2f}] {index[s]['lang']} 新: {index[s]['text'][:110]}")
    print(f"        已译: {index[ds]['text'][:110]}")
    print(f"        译文: {tr[ds][:60]}")
