# -*- coding: utf-8 -*-
"""三层去重：把 1316 条转写收敛成「唯一口播段」，给翻译用。

第 1 层：文本完全相同（归一化后）
第 2 层：花字相同 + 时长相同，且文本相似度 ≥ th
第 3 层：花字相同（时长不同），文本相似度 ≥ 0.95

输出 vo_unique.json: [{rid, text, lang, n, products, cards, keys}]
"""
import argparse, csv, json, re
from collections import defaultdict
from pathlib import Path

import openpyxl

D = Path(r"E:\video-download\analysis\data_20261123")
CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
XLSX = r"E:\video-download\analysis\out\2026-11-23_竞品素材拆解表.xlsx"


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / max(len(A | B), 1)


ap = argparse.ArgumentParser()
ap.add_argument("--th", type=float, default=0.85)
a = ap.parse_args()

asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
cls = json.loads((D / "vo_class.json").read_text(encoding="utf-8"))

# 序号 -> 花字/时长（按 weekly CSV 的行序）
rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
wb = openpyxl.load_workbook(XLSX, read_only=True)
ws = wb["1_素材总表"]
it = ws.iter_rows(values_only=True)
h = list(next(it))
ix = {x: i for i, x in enumerate(h)}
meta = {}
for r in it:
    if r[ix["序号"]] is None:
        continue
    i = int(r[ix["序号"]]) - 1
    meta[rows[i]["file"]] = dict(card=str(r[ix["画面文案（原文）"]] or "").strip(),
                                 dur=round(float(r[ix["时长s"]] or 0), 1),
                                 fmt=r[ix["形态"]])

items = []
for k, v in asr.items():
    if (cls.get(k) or {}).get("cls") != "vo":
        continue
    product, stem = k.split("|", 1)
    f = next((x["file"] for x in rows if x["stem"] == stem), "")
    m = meta.get(f, {})
    items.append(dict(key=k, product=product, file=f, text=v.get("text") or "",
                      lang=v.get("lang") or "", dur=float(v.get("dur") or 0),
                      card=norm(m.get("card", "")), card_raw=m.get("card", ""), fmt=m.get("fmt", "")))

print(f"真口播 {len(items)} 条")

# ---- 1 层：文本完全相同 ----
g1 = defaultdict(list)
for x in items:
    g1[norm(x["text"])].append(x)
print(f"第1层（文本完全相同）：{len(items)} -> {len(g1)} 段")

# ---- 2/3 层：花字+时长、或花字相同 ----
groups = list(g1.values())
groups.sort(key=len, reverse=True)          # 大的先当基准
merged = []
reps = []
for g in groups:
    t = norm(g[0]["text"])
    key = (g[0]["card"], round(g[0]["dur"], 0))
    hit = None
    for r in reps:
        if t == r["t"]:
            hit = r
            break
        if g[0]["card"] and g[0]["card"] == r["card"]:
            dt = abs(g[0]["dur"] - r["dur"])
            s = sim(t, r["t"])
            if (dt <= 0.4 and s >= a.th) or (dt > 0.4 and s >= 0.95):
                hit = r
                break
    if hit:
        hit["groups"].append(g)
    else:
        reps.append(dict(t=t, card=g[0]["card"], dur=g[0]["dur"], groups=[g], text=g[0]["text"],
                         lang=g[0]["lang"]))

out = []
for rid, r in enumerate(reps, 1):
    members = [x for g in r["groups"] for x in g]
    out.append(dict(rid=rid, text=r["text"], lang=r["lang"], card=r["card"],
                    n=len(members), products=sorted({x["product"] for x in members}),
                    keys=[x["key"] for x in members], dur=round(r["dur"], 1)))

(D / "vo_unique.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"第2/3层合并后：唯一段 {len(out)}（原 {len(items)} 条真口播）")
from collections import Counter
print("语种:", Counter(x["lang"] for x in out).most_common(12))
print("字符量:", f'{sum(len(x["text"]) for x in out):,}')
print("复投段（≥3 条）:", sum(1 for x in out if x["n"] >= 3))
print("只出现 1 次的段:", sum(1 for x in out if x["n"] == 1))
