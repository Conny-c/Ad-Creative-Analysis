# -*- coding: utf-8 -*-
"""验证「同一句花字 + 同一时长 => 同一条口播」这个假设，再用它算这期能省多少转写。

第一步（校准）：拿 11-16 期的 523 条——花字来自拆解表，口播来自 asr.json——
按 (花字, 时长±0.3s) 分组，看组内 ASR 文本到底有多一致。
第二步（外推）：拿 11-23 期的 1530 条，按同样的 key 分组，看唯一组数。
"""
import csv, json, re
from collections import defaultdict
from pathlib import Path

import openpyxl


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cards_from_xlsx(p):
    wb = openpyxl.load_workbook(p, read_only=True)
    ws = wb["1_素材总表"]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ix = {x: i for i, x in enumerate(h)}
    out = {}
    for r in it:
        if r[ix["序号"]] is None:
            continue
        out[int(r[ix["序号"]])] = (r[ix["产品"]], str(r[ix["画面文案（原文）"]] or "").strip(), float(r[ix["时长s"]] or 0))
    return out


def jacc(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / max(len(A | B), 1)


# ---------- 1. 用 11-16 校准 ----------
csv16 = list(csv.DictReader(open(r"E:\video-download\analysis\out\weekly_20261116_新增.csv", encoding="utf-8-sig")))
asr16 = json.loads(Path(r"E:\video-download\analysis\data_20261116\asr.json").read_text(encoding="utf-8"))
cards16 = cards_from_xlsx(r"E:\video-download\analysis\out\2026-11-16_竞品素材拆解表.xlsx")

rows16 = []
for i, r in enumerate(csv16, 1):
    key = f'{r["product"]}|{r["stem"]}'
    v = asr16.get(key) or {}
    prod, card, dur = cards16.get(i, (r["product"], "", float(r["duration"])))
    if not card or card in ("—", "-") or v.get("verdict") != "vo":
        continue
    rows16.append(dict(key=key, card=norm(card), card_raw=card, dur=round(dur, 1),
                       text=v.get("text") or "", product=prod))

g16 = defaultdict(list)
for x in rows16:
    g16[(x["card"], x["dur"])].append(x)

print(f"11-16 可校准样本 {len(rows16)} 条（有花字 + 有口播）")
multi = {k: v for k, v in g16.items() if len(v) > 1}
print(f"按 (花字, 时长) 分组：{len(g16)} 组，其中多条的 {len(multi)} 组，涉及 {sum(len(v) for v in multi.values())} 条")

same = 0
pairs = 0
scores = []
for k, v in multi.items():
    base = v[0]["text"]
    for x in v[1:]:
        pairs += 1
        s = jacc(base, x["text"])
        scores.append(s)
        if s >= 0.85:
            same += 1
scores.sort()
if scores:
    print(f"组内两两比对 {pairs} 对：文本相似度≥0.85 的 {same} 对（{same/pairs:.0%}）")
    print(f"  相似度中位 {scores[len(scores)//2]:.2f} / p25 {scores[len(scores)//4]:.2f} / p10 {scores[int(len(scores)*0.1)]:.2f}")

# ---------- 2. 外推 11-23 ----------
cards23 = cards_from_xlsx(r"E:\video-download\analysis\out\2026-11-23_竞品素材拆解表.xlsx")
rows23 = [(v[0], norm(v[1]), round(v[2], 1)) for v in cards23.values() if v[1] and v[1] not in ("—", "-")]
g23 = defaultdict(int)
for prod, card, dur in rows23:
    g23[(card, dur)] += 1
print(f"\n11-23 有花字 {len(rows23)} 条 -> (花字,时长) 唯一组 {len(g23)} 组")
print(f"  其中只有 1 条的组 {sum(1 for v in g23.values() if v == 1)}，多条组 {sum(1 for v in g23.values() if v > 1)}（涉及 {sum(v for v in g23.values() if v > 1)} 条）")
nocard = 1530 - len(rows23)
print(f"  无花字的 {nocard} 条按单条算 -> 需要转写 {len(g23) + nocard} 条（原 1530，省 {1530 - len(g23) - nocard} 条）")

# 再过一层：花字相同但时长不同的，也可能同稿
by_card = defaultdict(int)
for prod, card, dur in rows23:
    by_card[card] += 1
print(f"  仅按花字去重：{len(by_card)} 句（+无花字 {nocard}）-> {len(by_card) + nocard} 条")
