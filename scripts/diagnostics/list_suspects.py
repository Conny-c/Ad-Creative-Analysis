# -*- coding: utf-8 -*-
"""列出疑似误判：非本市场语种、以及命中 Whisper 常见幻觉串的行。"""
import json, re
from pathlib import Path

D = Path(r"E:\video-download\analysis\data_20261116")
asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
cls = json.loads((D / "vo_class.json").read_text(encoding="utf-8"))

SUSPECT_LANG = {"jw", "si", "km", "ru", "uk", "yi", "la", "nn", "su", "cy", "tl "}
HALLU_HINT = ["beadaholique", "amara", "subtitle", "字幕", "дынамичная", "динамичная",
              "позитивная музыка", "music", "thanks for watching"]

print("== 非本市场语种且当前判为有口播 ==")
for k, v in asr.items():
    c = (cls.get(k) or {}).get("cls")
    if c == "vo" and (v.get("lang") in SUSPECT_LANG):
        print(f'{v["lang"]:3} {k[:60]:60} :: {(v.get("text") or "")[:70]}')

print("\n== 命中幻觉串但判为有口播 ==")
for k, v in asr.items():
    c = (cls.get(k) or {}).get("cls")
    t = (v.get("text") or "").lower()
    if c == "vo" and any(h in t for h in HALLU_HINT):
        print(f'{v.get("lang"):3} {k[:60]:60} :: {(v.get("text") or "")[:70]}')
