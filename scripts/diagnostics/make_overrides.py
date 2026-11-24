# -*- coding: utf-8 -*-
"""人工复核覆盖表：自动判定明显错的，在这里按 key 改判，classify_vo.py 会读取。

只放「肉眼能确认」的：
  - 非本市场语种且 ASR 乱码      -> lyric（疑为音乐/人声）
  - Whisper 固定幻觉串            -> credit
  - 日文乱码、句读不成句（歌词）  -> lyric
"""
import json
from pathlib import Path

D = Path(r"E:\video-download\analysis\data_20261116")
asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
cls = json.loads((D / "vo_class.json").read_text(encoding="utf-8"))

over = {}

# 1) 日文乱码：同一段"わたりを揺れ…"反复出现，句读不成句，是歌词被听成字
for k, v in asr.items():
    t = v.get("text") or ""
    if "わたりを揺れ" in t:
        over[k] = {"cls": "lyric", "why": "日文乱码+成串重复，疑为歌词"}

# 2) Whisper 在静音/音乐上会固定输出这句
for k, v in asr.items():
    if "beadaholique" in (v.get("text") or "").lower():
        over[k] = {"cls": "credit", "why": "Whisper 固定幻觉串"}

# 3) 非本市场语种 + 乱码（僧伽罗语等），是音乐被乱转
for k, v in asr.items():
    if v.get("lang") in {"jw", "si", "km"}:
        over[k] = {"cls": "lyric", "why": f'语种检测为 {v.get("lang")}，非本市场，ASR 乱码'}

p = D / "vo_override.json"
p.write_text(json.dumps(over, ensure_ascii=False, indent=1), encoding="utf-8")
print("覆盖", len(over), "条 ->", p)
for k, o in over.items():
    print(f'  {o["cls"]:6} {o["why"]:26} {k[:56]} :: {(asr[k].get("text") or "")[:50]}')
