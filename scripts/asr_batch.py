# -*- coding: utf-8 -*-
"""1116 期口播转录：按周更台账(weekly_*_新增.csv / probe.csv)批量跑 ASR。

与 skill 里 asr.py 同一套口径（VAD 体检 → chars<20 无VAD复查 → 幻觉白名单），
区别是：直接吃 analysis 周更产出的 CSV、模型从工作区目录读、断点续跑、
按 md5 去重（同一条素材只转一次）。

用法:
  python asr_batch.py --csv out\weekly_20261116_新增.csv \
      --model analysis\models\medium --out analysis\data_20261116\asr.json

  只跑指定产品:  --products "Sugo,Tango"
  强制语种:      --lang tr
  复查单条:      --keys "Sugo|Sugo_xxx"
  体检模式(不写): --report-only
"""
import argparse, hashlib, json, os, subprocess, sys, time, wave
from pathlib import Path

import numpy as np

HALLU = [
    "thanks for watching", "altyazı m.k", "altyazi m.k", "редактор субтитров",
    "music", '["alive"]', "字幕由", "amara.org", "subscribe", "sous-titres",
    "...", "thank you for watching", "please subscribe",
]


def is_hallu(text):
    t = (text or "").strip().lower()
    if not t:
        return "empty"
    for h in HALLU:
        if h in t:
            return h
    return ""


def load_wav(p, sr=16000):
    with wave.open(str(p), "rb") as w:
        rate = w.getframerate()
        data = w.readframes(w.getnframes())
    if rate != sr:
        raise ValueError(f"{p}: expect {sr}Hz got {rate}")
    return np.frombuffer(data, dtype=np.int16).astype("float32") / 32768.0


def key_of(r):
    return f'{r["product"]}|{r["stem"]}'


def fp_codes(path):
    """每秒一个 8bit 能量码（十六进制串），跟 build_voice_ledger.py 保持一致。"""
    try:
        with wave.open(str(path), "rb") as w:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--model", required=True, help="本地模型目录（含 model.bin）")
    ap.add_argument("--out", default="asr.json")
    ap.add_argument("--audio", default="audio")
    ap.add_argument("--lang", default="")
    ap.add_argument("--products", default="")
    ap.add_argument("--keys", default="")
    ap.add_argument("--novad", action="store_true")
    ap.add_argument("--no-retry", action="store_true")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="已转过的也重跑（复查用）")
    ap.add_argument("--keys-file", default="", help="一行一个 key 的文件")
    ap.add_argument("--ledger", default=r"E:\video-download\analysis\out\voice_ledger.csv",
                    help="累积语音台账；命中 md5 或音频指纹就继承，不重转")
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()

    import csv as _csv
    rows = list(_csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    rows = [r for r in rows if r.get("path") and Path(r["path"]).exists()]
    if a.products:
        want = {p.strip() for p in a.products.split(",") if p.strip()}
        rows = [r for r in rows if r["product"] in want]
    if a.keys:
        want = {k.strip() for k in a.keys.split(",")}
        rows = [r for r in rows if key_of(r) in want]
    if a.keys_file:
        want = {l.strip() for l in Path(a.keys_file).read_text(encoding="utf-8").splitlines() if l.strip()}
        rows = [r for r in rows if key_of(r) in want]

    # md5 去重：同一条素材只转一次
    seen, uniq, dups = {}, [], {}
    for r in rows:
        h = r.get("md5") or hashlib.md5(Path(r["path"]).read_bytes()).hexdigest()
        if h in seen:
            dups.setdefault(seen[h], []).append(key_of(r))
        else:
            seen[h] = key_of(r)
            uniq.append(r)
    rows = uniq
    if a.limit:
        rows = rows[: a.limit]

    out = Path(a.out)
    res = json.loads(out.read_text(encoding="utf-8")) if out.exists() and not a.report_only else {}

    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(a.model, device="cpu", compute_type="int8",
                         cpu_threads=a.threads, local_files_only=True)
    print(f"loaded {a.model} in {time.time()-t0:.1f}s | 待转 {len(rows)} 条 "
          f"(去重掉 {sum(len(v) for v in dups.values())} 条重复)", flush=True)

    aud = Path(a.audio)
    aud.mkdir(parents=True, exist_ok=True)

    # ---- 累积台账：md5 命中 / 音频指纹命中 就继承 ----
    led_md5, led_fp = {}, []
    if not a.no_ledger and Path(a.ledger).exists():
        import csv as _c
        for x in _c.DictReader(open(a.ledger, encoding="utf-8-sig")):
            if x.get("md5"):
                led_md5[x["md5"]] = x
            if len(x.get("fp_codes") or "") >= 4:
                s = shingles(x["fp_codes"])
                if len(s) >= 6:
                    led_fp.append((s, float(x.get("dur") or 0), x))
        print(f"台账 {Path(a.ledger).name}: md5 {len(led_md5)} 条 / 指纹 {len(led_fp)} 条", flush=True)

    def wav_of(r):
        wav = aud / (r["stem"][:80] + ".wav")
        if not wav.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", r["path"], "-vn",
                            "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)],
                           capture_output=True)
        return wav

    def lookup(r):
        """返回台账命中的一行，或 None"""
        if r.get("md5") and r["md5"] in led_md5:
            return led_md5[r["md5"]], "md5"
        if not led_fp:
            return None, ""
        wav = wav_of(r)
        if not wav.exists():
            return None, ""
        codes = fp_codes(wav)
        if not codes:
            return None, ""
        s = shingles(codes)
        d = float(r.get("duration") or 0)
        for ls, ld, row in led_fp:
            if abs(ld - d) > max(1.0, 0.08 * max(ld, d)):
                continue
            if len(s & ls) / max(len(s | ls), 1) >= 0.75:
                return row, "fp"
        return None, ""

    def run(r, vad):
        wav = wav_of(r)
        audio = load_wav(wav)
        segs, info = model.transcribe(audio, language=(a.lang or None), vad_filter=vad,
                                      beam_size=5, condition_on_previous_text=False,
                                      no_speech_threshold=0.6)
        parts = [{"t0": round(s.start, 2), "t1": round(s.end, 2), "text": s.text.strip()}
                 for s in segs if s.text.strip()]
        return " ".join(p["text"] for p in parts), parts, info.language

    done = miss = 0
    t_start = time.time()
    for i, r in enumerate(rows, 1):
        k = key_of(r)
        if k in res and res[k].get("verdict"):
            done += 1 if res[k]["verdict"] == "vo" else 0
            miss += 1 if res[k]["verdict"] == "none" else 0
            continue
        hit, how = lookup(r)
        if hit:
            res[k] = dict(product=r["product"], file=r["file"], stem=r["stem"],
                          dur=float(r.get("duration") or 0), md5=r.get("md5", ""),
                          lang=hit.get("lang", ""), text=hit.get("text", ""), segs=[],
                          chars=int(hit.get("chars") or 0),
                          verdict=hit.get("verdict") or ("vo" if hit.get("text") else "none"),
                          hit="", inherited=how)
            done += 1 if res[k]["verdict"] == "vo" else 0
            miss += 1 if res[k]["verdict"] == "none" else 0
            print(f'[{i}/{len(rows)}] 继承({how}) {k} :: {(hit.get("text") or "")[:60]}', flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            continue
        try:
            text, parts, lang = run(r, not a.novad)
            # 只有「有一点字但不够」才值得关 VAD 复查；0-4 字基本都是纯音乐，复查也是白跑
            if 5 <= len(text) < 20 and not a.no_retry and not a.novad:
                t2, p2, l2 = run(r, vad=False)
                if len(t2) > len(text):
                    text, parts, lang = t2, p2, l2
            verdict = "vo" if len(text) >= 20 else "none"
            hit = "" if verdict == "vo" else (is_hallu(text) or "empty")
            res[k] = dict(product=r["product"], file=r["file"], stem=r["stem"],
                          dur=float(r.get("duration") or 0), md5=r.get("md5", ""),
                          lang=lang, text=text, segs=parts, chars=len(text),
                          verdict=verdict, hit=hit)
            if verdict == "vo":
                done += 1
            else:
                miss += 1
            flag = "VO " if verdict == "vo" else "---"
            el = time.time() - t_start
            n = i
            eta = el / n * (len(rows) - n) / 60 if n else 0
            print(f'[{i}/{len(rows)}] {flag} {k} lang={lang} chars={len(text)} '
                  f'eta={eta:.0f}min :: {text[:80]}', flush=True)
            if not a.report_only:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f'[{i}/{len(rows)}] ERR {k}: {type(e).__name__} {e}', flush=True)
            res[k] = dict(product=r["product"], file=r["file"], stem=r["stem"],
                          dur=float(r.get("duration") or 0), md5=r.get("md5", ""),
                          lang="", text="", segs=[], chars=0, verdict="error", hit=str(e))
            out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    tot = len([v for v in res.values() if v.get("verdict") in ("vo", "none")])
    vo = len([v for v in res.values() if v.get("verdict") == "vo"])
    print(f"\n== 完成 {tot} 条：有口播 {vo} / 无人声 {tot - vo} | 用时 {(time.time()-t_start)/60:.1f} min")
    print("saved", out)


if __name__ == "__main__":
    main()
