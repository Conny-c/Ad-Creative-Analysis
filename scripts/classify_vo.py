# -*- coding: utf-8 -*-
"""把 asr_batch 的原始结果再分一层：真口播 / 歌词 / 署名幻觉 / 无人声。

ASR 有输出 ≠ 有文案。ad-library 里大量成片是「BGM + 花字」，whisper 会把歌听成字。
判据（对齐 skill 的 classify_vo.py）：
  命中幻觉白名单 / [..] 曲目署名            -> credit
  music/song 类词占比高，或词重复率 < 0.55 且短   -> lyric
  其余 length>=20                            -> vo
  不足 20 字且没内容                          -> none
"""
import argparse, json, re
from collections import Counter
from pathlib import Path

HALLU = ["thanks for watching", "thank you for watching", "altyazı m.k", "altyazi m.k",
         "редактор субтитров", "amara.org", "subscribe", "字幕由", "sous-titres",
         "please subscribe", "thanks for watch"]
MUSIC_WORDS = {"music", "musica", "música", "song", "lied", "muzik", "müzik", "음악",
               "音乐", "音樂", "bgm", "instrumental", "[music]", "ding", "oh", "ah"}


def tokens(text, lang):
    t = (text or "").strip().lower()
    if lang in ("ja", "zh", "th", "ko"):
        # 无空格语种：用字符二元组近似词
        s = re.sub(r"\s+", "", t)
        return [s[i:i + 2] for i in range(max(len(s) - 1, 1))]
    return re.findall(r"[\w']+", t)


def classify(v):
    text = (v or "").get("text") or ""
    lang = (v or "").get("lang") or ""
    low = text.lower().strip()
    chars = len(text.strip())
    if (v or {}).get("verdict") == "error":
        return "error", "asr 报错"
    if chars == 0:
        return "none", "空音频"
    for h in HALLU:
        if h in low:
            return "credit", f"幻觉白名单:{h}"
    if chars < 20:
        return "none", "过短"
    tk = tokens(text, lang)
    if tk:
        ratio = len(set(tk)) / len(tk)
        music_share = sum(1 for x in tk if x in MUSIC_WORDS) / len(tk)
        if music_share >= 0.4:
            return "lyric", f"music词占比{music_share:.0%}"
        if ratio < 0.55 and chars < 160:
            return "lyric", f"重复率{ratio:.0%}"
    return "vo", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default=r"E:\video-download\analysis\data_20261116\asr.json")
    ap.add_argument("--out", default=r"E:\video-download\analysis\data_20261116\vo_class.json")
    a = ap.parse_args()
    asr = json.loads(Path(a.asr).read_text(encoding="utf-8"))
    ov_path = Path(a.asr).parent / "vo_override.json"
    over = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    res = {}
    for k, v in asr.items():
        cls, why = classify(v)
        if k in over:
            cls, why = over[k]["cls"], over[k]["why"]
        res[k] = dict(cls=cls, why=why, lang=v.get("lang"), chars=v.get("chars"),
                      dur=v.get("dur"), text=(v.get("text") or "")[:200])
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    c = Counter(v["cls"] for v in res.values())
    print(f"共 {len(res)} 条 ->", dict(c))
    print("保存", a.out)
    for k, v in list(res.items()):
        if v["cls"] in ("lyric", "credit"):
            print(f'  {v["cls"]:6} {k[:52]:52} {v["why"]:16} :: {(v["text"] or "")[:50]}')


if __name__ == "__main__":
    main()
