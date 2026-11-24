# -*- coding: utf-8 -*-
"""抽查：按形态列出判为「有口播」的样本，检查是否把 BGM 当人声。"""
import sys
from collections import Counter
import openpyxl

p = r"E:\video-download\analysis\out\2026-11-16_口播转录表.xlsx"
wb = openpyxl.load_workbook(p, read_only=True)
ws = wb["1_口播总表"]
it = ws.iter_rows(values_only=True)
hdr = next(it)
ix = {h: i for i, h in enumerate(hdr)}
rows = [r for r in it if r[ix["序号"]] is not None]

want = sys.argv[1] if len(sys.argv) > 1 else "图文卡点"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
print(f"形态={want}")
shown = 0
for r in rows:
    if r[ix["形态"]] == want and r[ix["口播判定"]] == "有口播":
        print(f'{r[ix["序号"]]:>4} {r[ix["产品"]]:<10} {r[ix["口播语言"]]:<3} {r[ix["口播字数"]]:>4}字 | '
              f'{(r[ix["口播原文（ASR）"]] or "")[:100]}')
        shown += 1
        if shown >= n:
            break
print("判定分布:", Counter(r[ix["口播判定"]] for r in rows).most_common())
