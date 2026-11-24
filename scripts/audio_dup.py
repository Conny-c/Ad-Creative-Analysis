# -*- coding: utf-8 -*-
"""音频查重（生产版）：抽音轨 → 指纹 → 聚类 → 给出「可省多少条转写」。

    python audio_dup.py --csv out\weekly_20261123_新增.csv \
        --audio data_20261123\audio --out data_20261123\audio_dup.json \
        --extract --workers 16 --th 0.7

输出：
    每个 cluster 的代表条 + 成员，savings = 总条数 - 组数
"""
import argparse, csv, json, subprocess, wave
from collections import defaultdict
from pathlib import Path

import numpy as np

FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"


def band_energies(x, sr=16000, win=512):
    if len(x) < win:
        x = np.pad(x, (0, win - len(x)))
    n = 1 + (len(x) - win) // win
    idx = np.arange(win)[None, :] + win * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(win)[None, :]
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1 / sr)
    edges = [0, 250, 500, 1000, 2000, 3000, 4500, 6000, 8000]
    out = np.zeros((n, len(edges) - 1), dtype=np.float32)
    for i in range(len(edges) - 1):
        m = (freqs >= edges[i]) & (freqs < edges[i + 1])
        out[:, i] = spec[:, m].mean(axis=1) if m.any() else 0
    return np.log1p(out * 1e3)


def fingerprint(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        raise ValueError(f"{path}: {sr}Hz")
    E = band_energies(x)
    per_sec = max(1, int(16000 / 512))
    m = (len(E) // per_sec) * per_sec
    if m == 0:
        return set()
    E = E[:m].reshape(m // per_sec, per_sec, -1).mean(axis=1)
    q = np.clip((E - E.mean(axis=0, keepdims=True)) / (E.std(axis=0, keepdims=True) + 1e-6), -2, 2)
    bits = (q > 0).astype(np.uint32)
    code = bits.dot(1 << np.arange(8))
    return {int((code[i] << 16) | (code[i + 1] << 8) | code[i + 2]) for i in range(len(code) - 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--th", type=float, default=0.7)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    aud = Path(a.audio)
    aud.mkdir(parents=True, exist_ok=True)

    todo = []
    for r in rows:
        wav = aud / (r["stem"][:80] + ".wav")
        if not wav.exists() and a.extract:
            todo.append((r["path"], wav))
    print(f"待抽音轨 {len(todo)} 条 / 总 {len(rows)} 条", flush=True)

    if todo:
        import concurrent.futures as cf

        def ex(pair):
            src, dst = pair
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
                            "-ar", "16000", "-f", "wav", str(dst)], capture_output=True)
            return dst.exists()

        with cf.ThreadPoolExecutor(a.workers) as pool:
            for i, ok in enumerate(pool.map(ex, todo), 1):
                if i % 200 == 0:
                    print(f"  抽音轨 {i}/{len(todo)}", flush=True)
        print("抽音轨完成", flush=True)

    items = []
    for r in rows:
        wav = aud / (r["stem"][:80] + ".wav")
        if not wav.exists():
            continue
        fp = fingerprint(wav)
        if fp:
            items.append(dict(key=f'{r["product"]}|{r["stem"]}', fp=fp, product=r["product"],
                              dur=float(r["duration"]), file=r["file"]))
    print(f"指纹 {len(items)} 条", flush=True)

    n = len(items)
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    pairs = 0
    for i in range(n):
        fi = items[i]["fp"]
        if len(fi) < 6:          # 太短（<9s）指纹不稳，容易误配
            continue
        for j in range(i + 1, n):
            fj = items[j]["fp"]
            if len(fj) < 6:
                continue
            d1, d2 = items[i]["dur"], items[j]["dur"]
            if abs(d1 - d2) > max(1.0, 0.08 * max(d1, d2)):   # 同一条音频时长必须接近
                continue
            s = len(fi & fj) / max(len(fi | fj), 1)
            if s >= a.th:
                pairs += 1
                ri, rj = find(i), find(j)
                if ri != rj:
                    par[ri] = rj
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    multi = [g for g in groups.values() if len(g) > 1]
    savings = sum(len(g) - 1 for g in multi)

    out = dict(total=n, pairs=pairs, clusters=len(multi),
               cluster_rows=sum(len(g) for g in multi), savings=savings,
               groups=[[items[i]["key"] for i in sorted(g)] for g in sorted(multi, key=len, reverse=True)])
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n指纹重复对 {pairs} | 重复组 {len(multi)} | 涉及 {sum(len(g) for g in multi)} 条 | "
          f"可省转写 {savings} 条（{savings/max(n,1):.1%}）")
    for g in sorted(multi, key=len, reverse=True)[:5]:
        print(f"  {len(g)} 条: {items[g[0]]['product']} | {[round(items[i]['dur'],1) for i in g]}")


if __name__ == "__main__":
    main()
