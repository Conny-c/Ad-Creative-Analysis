# -*- coding: utf-8 -*-
"""L2: 节奏与声音画像
- 节奏：5fps/128px 帧差，统计「画面显著变化次数」，比 scene 阈值更能抓渐变/叠化
- 声音：8k 单声道能量包络 → RMS / 静音比 / 包络变异系数 / 4Hz 语音调制指数
"""
import csv, json, wave, subprocess, tempfile, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(os.environ.get("SUGO_WORK", str(Path(__file__).resolve().parent.parent)))
FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"
TMP = Path(os.environ.get("SUGO_TMP_DIR", str(ROOT / "assets" / "_tmp")))


def rhythm(src, dur):
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-vf", "fps=5,scale=128:128", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    r = subprocess.run(cmd, capture_output=True)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    if buf.size == 0 or buf.size % (128 * 128) != 0:
        return {}
    frames = buf.reshape(-1, 128, 128).astype(np.float32)
    if len(frames) < 3:
        return {}
    d = np.abs(np.diff(frames, axis=0))
    diffs = d.mean(axis=(1, 2))
    changed = (d > 25).mean(axis=(1, 2))  # 显著变化像素占比，抓局部换字/换画面
    th = max(float(changed.mean() + 3 * changed.std()), 0.05)
    trans = int((changed > th).sum())
    return {
        "frames": int(len(frames)),
        "diffs_mean": round(float(diffs.mean()), 2),
        "changed_max": round(float(changed.max()), 3),
        "trans": trans,
        "trans_per_10s": round(trans / max(dur, 0.1) * 10, 2),
        "shot_avg": round(dur / max(trans + 1, 1), 2),
    }


def audio(src):
    with tempfile.TemporaryDirectory(dir=TMP, ignore_cleanup_errors=True) as td:
        wav = Path(td) / "a.wav"
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
               "-vn", "-ac", "1", "-ar", "8000", str(wav)]
        subprocess.run(cmd, capture_output=True)
        if not wav.exists() or wav.stat().st_size < 4000:
            return {}
        with wave.open(str(wav)) as w:
            sr, n = w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size < sr:
        return {}
    hop = sr // 100
    m = x.size // hop * hop
    env = np.sqrt((x[:m].reshape(-1, hop) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(env + 1e-9)
    rms = float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))
    silence = float((db < -45).mean())
    cv = float(env.std() / (env.mean() + 1e-9))
    e = env - env.mean()
    f = np.fft.rfftfreq(len(e), d=0.01)
    P = np.abs(np.fft.rfft(e)) ** 2
    band = P[(f >= 2) & (f <= 8)].sum()
    tot = P[(f > 0.3) & (f <= 20)].sum() + 1e-12
    return {
        "rms_db": round(rms, 1),
        "silence_ratio": round(silence, 2),
        "env_cv": round(cv, 2),
        "speech_mod": round(float(band / tot), 2),
    }


def one(row):
    src = Path(row["path"])
    dur = float(row["duration"])
    out = {"file": row["file"]}
    try:
        out.update(rhythm(src, dur))
    except Exception as e:
        out["rhythm_err"] = str(e)[:80]
    try:
        out.update(audio(src))
    except Exception as e:
        out["audio_err"] = str(e)[:80]
    return out


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    DATA = Path(os.environ.get("SUGO_DATA_DIR", str(ROOT / "data")))
    rows = list(csv.DictReader(open(DATA / "probe.csv", encoding="utf-8-sig")))
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(one, rows))
    Path(DATA / "rhythm.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    okr = [r for r in res if "trans" in r]
    oka = [r for r in res if "rms_db" in r]
    print("rhythm ok:", len(okr), "audio ok:", len(oka))
    if okr:
        tp = np.array([r["trans_per_10s"] for r in okr])
        print("trans_per_10s p25/50/75/90:", np.percentile(tp, [25, 50, 75, 90]).round(2))
        sa = np.array([r["shot_avg"] for r in okr])
        print("shot_avg p25/50/75:", np.percentile(sa, [25, 50, 75]).round(2))
    if oka:
        print("speech_mod p25/50/75:", np.percentile([r["speech_mod"] for r in oka], [25, 50, 75]).round(2))
        print("silence p25/50/75:", np.percentile([r["silence_ratio"] for r in oka], [25, 50, 75]).round(2))
        print("rms p50:", round(float(np.percentile([r["rms_db"] for r in oka], 50)), 1))


if __name__ == "__main__":
    main()
