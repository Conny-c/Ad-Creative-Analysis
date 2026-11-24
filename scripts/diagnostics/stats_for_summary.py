# -*- coding: utf-8 -*-
"""给小结取数：产品口径、只有口播的分布、口播长度、复投组。"""
from collections import Counter, defaultdict
import openpyxl

p = r"E:\video-download\analysis\out\2026-11-16_口播转录表.xlsx"
wb = openpyxl.load_workbook(p, read_only=True)
ws = wb["1_口播总表"]
it = ws.iter_rows(values_only=True)
h = list(next(it))
ix = {x: i for i, x in enumerate(h)}
rows = [r for r in it if r[ix["序号"]] is not None]

def card(r):
    return (r[ix["画面文案（花字）"]] or "").strip() not in ("", "—", "-", "无")

by_p = defaultdict(lambda: [0, 0, 0, 0])  # 总数, 有口播, 只有口播, 字数合计
for r in rows:
    p_ = r[ix["产品"]]
    b = by_p[p_]
    b[0] += 1
    if r[ix["口播判定"]] == "有口播":
        b[1] += 1
        b[3] += r[ix["口播字数"]] or 0
        if not card(r):
            b[2] += 1
print("产品 | 素材 | 有口播 | 有口播率 | 只有口播 | 平均口播字数")
for p_, (n, v, o, ch) in sorted(by_p.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
    print(f"{p_:<12} {n:>4} {v:>6} {v/n:>7.0%} {o:>8} {ch/max(v,1):>10.0f}")

print("\n只有口播的 31 条按形态/产品:")
c = Counter((r[ix["形态"]], r[ix["产品"]]) for r in rows
            if r[ix["口播判定"]] == "有口播" and not card(r))
for k, n in c.most_common(12):
    print("  ", k, n)

print("\n复投组(≥3条):")
ws2 = wb["2_口播库"]
it2 = ws2.iter_rows(values_only=True)
next(it2)
for r in it2:
    if r[0] and r[0] >= 3:
        print(f'  {r[0]}条 {r[1]:<14} {r[2]:<3} {r[3][:70]}')
