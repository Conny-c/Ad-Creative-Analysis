# -*- coding: utf-8 -*-
"""交付前自检：译文覆盖率、复投组、口播vs花字、异常行。"""
from collections import Counter
import openpyxl

p = r"E:\video-download\analysis\out\2026-11-16_口播转录表.xlsx"
wb = openpyxl.load_workbook(p, read_only=True)

ws = wb["1_口播总表"]
it = ws.iter_rows(values_only=True)
hdr = list(next(it))
ix = {h: i for i, h in enumerate(hdr)}
rows = [r for r in it if r[ix["序号"]] is not None]
vo = [r for r in rows if r[ix["口播判定"]] == "有口播"]
nozh = [r for r in vo if not (r[ix["口播中文（译）"]] or "").strip()]
print(f"总表 {len(rows)} | 有口播 {len(vo)} | 缺中文译 {len(nozh)}")
for r in nozh[:5]:
    print("  缺译:", r[ix["序号"]], r[ix["产品"]], (r[ix["口播原文（ASR）"]] or "")[:60])

print("\n== 复投口播 TOP8（同一条口播换画面）==")
ws2 = wb["2_口播库"]
it2 = ws2.iter_rows(values_only=True)
next(it2)
lib = [r for r in it2 if r[0]]
for r in lib[:8]:
    print(f'{r[0]:>3}条 {r[1]:<18} {r[2]:<3} {r[3][:58]}')

ws5 = wb["5_口播vs花字"]
print("\n== 口播 vs 花字 ==")
for r in ws5.iter_rows(min_row=2, max_row=5, values_only=True):
    if r[0]:
        print(f"  {r[0]:<8} {r[1]:>4}  {r[2]}")

ws4 = wb["4_统计"]
print("\n== 统计首行 ==")
print(ws4.cell(row=1, column=1).value)
