# -*- coding: utf-8 -*-
"""用 11-16 期的实测结果，看现有音频特征能不能在上 ASR 之前把「没人声」的挑出来。

如果 speech_mod / silence_ratio / rms_db / env_cv 能把 vo 和 none 分开，
就可以先跑一遍几十秒的音频体检，只对可能有口播的片段上 ASR。
"""
import csv, json
from collections import Counter
from pathlib import Path

import numpy as np

ASR = Path(r"E:\video-download\analysis\data_20261116\asr.json")
CLS = Path(r"E:\video-download\analysis\data_20261116\vo_class.json")
CSV16 = r"E:\video-download\analysis\out\weekly_20261116_新增.csv"

asr = json.loads(ASR.read_text(encoding="utf-8"))
cls = json.loads(CLS.read_text(encoding="utf-8"))
rows = list(csv.DictReader(open(CSV16, encoding="utf-8-sig")))

# weekly 里的 rhythm 字段
feat = ["rms_db", "silence_ratio", "env_cv", "speech_mod"]
data = {"vo": {f: [] for f in feat}, "none": {f: [] for f in feat}}
for i, r in enumerate(rows, 1):
    k = f'{r["product"]}|{r["stem"]}'
    c = (cls.get(k) or {}).get("cls")
    if c not in ("vo", "none"):
        continue
    for f in feat:
        try:
            data[c][f].append(float(r[f]))
        except Exception:
            pass


def stat(name, a, b):
    if not a or not b:
        return
    a, b = np.array(a), np.array(b)
    print(f"{name:<14} vo 中位 {np.median(a):7.2f} (p10 {np.percentile(a,10):6.2f}, p90 {np.percentile(a,90):6.2f})"
          f" | none 中位 {np.median(b):7.2f} (p10 {np.percentile(b,10):6.2f}, p90 {np.percentile(b,90):6.2f})")


print(f"样本：vo {len(data['vo']['rms_db'])} 条 / none {len(data['none']['rms_db'])} 条\n")
for f in feat:
    stat(f, data["vo"][f], data["none"][f])

# 用 speech_mod 阈值扫一遍，看能筛掉多少 none、误杀多少 vo
SM = [(float(r["speech_mod"]), (cls.get(f'{r["product"]}|{r["stem"]}') or {}).get("cls"))
      for r in rows if r.get("speech_mod")]
SM = [(s, c) for s, c in SM if c in ("vo", "none")]
print("\nspeech_mod 阈值扫描（判 none 的门槛）：")
for th in (0.25, 0.3, 0.33, 0.35, 0.4):
    drop_none = sum(1 for s, c in SM if s < th and c == "none")
    kill_vo = sum(1 for s, c in SM if s < th and c == "vo")
    print(f"  <{th}: 筛掉 none {drop_none}/{sum(1 for s,c in SM if c=='none')}，"
          f"误杀 vo {kill_vo}/{sum(1 for s,c in SM if c=='vo')}")
