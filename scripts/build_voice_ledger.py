# -*- coding: utf-8 -*-
"""累积语音台账：把每期的 asr 结果、判定、译文、音频指纹并进一张表。

下周跑新增时，先按 md5 查这张表，再按音频指纹（fp_codes 重算 shingle）查，
命中就继承，不用重新转写。

    python build_voice_ledger.py --batch 20261123 --work analysis
    python build_voice_ledger.py --all          # 把有 asr.json 的期号全部并入
"""
import argparse, csv, json, wave
from pathlib import Path

import numpy as np

LEDGER = "voice_ledger.csv"
COLS = ["期号", "md5", "product", "file", "stem", "dur", "lang", "verdict", "chars",
        "text", "zh", "fp_codes", "src"]


def fp_codes(wav_path):
    """每秒一个 8bit 能量码（十六进制串）；同时能还原 shingle 做相似度。"""
    try:
        with wave.open(str(wav_path), "rb") as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    except Exception:
        return ""
    if sr != 16000 or len(x) < 512 * 3:
        return ""
    win = 512
    n = 1 + (len(x) - win) // win
    idx = np.arange(win)[None, :] + win * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(win)[None, :]
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1 / sr)
    edges = [0, 250, 500, 1000, 2000, 3000, 4500, 6000, 8000]
    E = np.zeros((n, len(edges) - 1), dtype=np.float32)
    for i in range(len(edges) - 1):
        m = (freqs >= edges[i]) & (freqs < edges[i + 1])
        E[:, i] = spec[:, m].mean(axis=1) if m.any() else 0
    E = np.log1p(E * 1e3)
    per = int(16000 / win)
    m = (len(E) // per) * per
    if m == 0:
        return ""
    E = E[:m].reshape(m // per, per, -1).mean(axis=1)
    q = np.clip((E - E.mean(axis=0, keepdims=True)) / (E.std(axis=0, keepdims=True) + 1e-6), -2, 2)
    bits = (q > 0).astype(np.uint32)
    code = bits.dot(1 << np.arange(8))
    return "".join(f"{c:02x}" for c in code)


def shingles(codes_str, k=3):
    if not codes_str or len(codes_str) < 2 * k:
        return set()
    cs = [int(codes_str[i:i + 2], 16) for i in range(0, len(codes_str), 2)]
    return {tuple(cs[i:i + k]) for i in range(len(cs) - k + 1)}


def build(work, period):
    work = Path(work)
    data = work / f"data_{period}"
    asr_p = data / "asr.json"
    if not asr_p.exists():
        print(f"[skip] {period}: 没有 asr.json")
        return []
    asr = json.loads(asr_p.read_text(encoding="utf-8"))
    cls = json.loads((data / "vo_class.json").read_text(encoding="utf-8")) if (data / "vo_class.json").exists() else {}
    zh = json.loads((data / "vo_zh.json").read_text(encoding="utf-8")) if (data / "vo_zh.json").exists() else {}
    dmap = json.loads((data / "dedupe_map.json").read_text(encoding="utf-8")) if (data / "dedupe_map.json").exists() else {}

    # 本周期的原始清单（含被去重跳过的），用于拿 md5
    cand = sorted(work.joinpath("out").glob(f"weekly_{period}_新增.csv"))
    if not cand:
        print(f"[skip] {period}: 没有 weekly CSV")
        return []
    rows = list(csv.DictReader(open(cand[0], encoding="utf-8-sig")))
    by_file = {r["file"]: r for r in rows}
    skip = dmap.get("skip_map", {})

    aud = data / "audio"
    out = []
    for r in rows:
        key = f'{r["product"]}|{r["stem"]}'
        src_key = key
        src = "asr"
        if key not in asr and r["file"] in skip:      # 被去重跳过的：继承代表条
            rep = skip[r["file"]]
            rep_row = by_file.get(rep)
            if rep_row:
                src_key = f'{rep_row["product"]}|{rep_row["stem"]}'
                src = "dedup"
        v = asr.get(src_key) or {}
        wav = aud / (r["stem"][:80] + ".wav")
        out.append(dict(
            期号=period, md5=r.get("md5", ""), product=r["product"], file=r["file"],
            stem=r["stem"], dur=round(float(r.get("duration") or 0), 2),
            lang=v.get("lang", ""), verdict=(cls.get(src_key) or {}).get("cls") or v.get("verdict", ""),
            chars=v.get("chars", 0), text=(v.get("text") or "").replace("\n", " "),
            zh=(zh.get(src_key) or zh.get(key) or "").replace("\n", " "),
            fp_codes=fp_codes(wav) if wav.exists() else "", src=src,
        ))
    print(f"{period}: {len(out)} 条（转写 {sum(1 for x in out if x['src']=='asr')} + 继承 {sum(1 for x in out if x['src']=='dedup')}）"
          f"，指纹 {sum(1 for x in out if x['fp_codes'])} 条")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=r"E:\video-download\analysis")
    ap.add_argument("--batch", default="")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    work = Path(a.work)
    periods = []
    if a.all:
        for d in sorted(work.glob("data_*")):
            p = d.name.replace("data_", "")
            if p.isdigit():
                periods.append(p)
    else:
        periods = [a.batch]

    all_rows = []
    for p in periods:
        all_rows += build(work, p)
    if not all_rows:
        print("没有可写入的数据")
        return

    lp = work / "out" / LEDGER
    old = []
    if lp.exists():
        old = [r for r in csv.DictReader(open(lp, encoding="utf-8-sig"))]
        keep = {(r["期号"], r["md5"]) for r in all_rows}
        old = [r for r in old if (r["期号"], r["md5"]) not in keep]
    merged = old + all_rows
    with open(lp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in merged:
            w.writerow({k: r.get(k, "") for k in COLS})
    print(f"\n台账 {lp.name}: 本次写入 {len(all_rows)}，历史 {len(old)}，合计 {len(merged)}")


if __name__ == "__main__":
    main()
