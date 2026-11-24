# -*- coding: utf-8 -*-
"""音频指纹：找「同一段声音、不同画面」的素材（比画面查重更强，直接对应口播相同）。

做法：16k 单声道 → 512 点 STFT → 8 个频带能量 → 每秒平均 → 4bit 量化 → 16bit 每秒指纹
      → 3 秒滑窗做 shingle → 两两比 Jaccard。

先拿 11-16 期（wav 已缓存）验证：指纹相似度高的，口播文本是不是也一致。
"""
import json, wave
from collections import defaultdict
from pathlib import Path

import numpy as np


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


def fingerprint(wav_path):
    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        raise ValueError(f"{wav_path}: {sr}Hz")
    E = band_energies(x)                      # (frames, 8)
    per_sec = max(1, int(16000 / 512))        # 每秒帧数
    m = (len(E) // per_sec) * per_sec
    if m == 0:
        return set()
    E = E[:m].reshape(m // per_sec, per_sec, -1).mean(axis=1)   # (秒, 8)
    q = np.clip((E - E.mean(axis=0, keepdims=True)) / (E.std(axis=0, keepdims=True) + 1e-6), -2, 2)
    bits = (q > 0).astype(np.uint32)                            # 8 bit / 秒
    code = bits.dot(1 << np.arange(8))                          # 每秒一个 8bit code
    sh = {int((code[i] << 16) | (code[i + 1] << 8) | code[i + 2]) for i in range(len(code) - 2)}
    return sh


def main():
    D = Path(r"E:\video-download\analysis\data_20261116")
    asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
    import csv
    rows = list(csv.DictReader(open(r"E:\video-download\analysis\out\weekly_20261116_新增.csv", encoding="utf-8-sig")))

    items = []
    for r in rows:
        wav = D / "audio" / (r["stem"][:80] + ".wav")
        if not wav.exists():
            continue
        fp = fingerprint(wav)
        if fp:
            items.append((f'{r["product"]}|{r["stem"]}', fp, asr.get(f'{r["product"]}|{r["stem"]}', {}).get("text") or ""))
    print(f"指纹 {len(items)} 条")

    def jac(a, b):
        return len(a & b) / max(len(a | b), 1)

    def txt(a, b):
        A, B = set(a.split()), set(b.split())
        return len(A & B) / max(len(A | B), 1)

    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            s = jac(items[i][1], items[j][1])
            if s >= 0.5:
                pairs.append((s, txt(items[i][2], items[j][2]), items[i][0], items[j][0]))
    pairs.sort(reverse=True)
    print(f"指纹相似度≥0.5 的对: {len(pairs)}")
    if pairs:
        ss = np.array([p[0] for p in pairs])
        ts = np.array([p[1] for p in pairs])
        print(f"  指纹相似度中位 {np.median(ss):.2f} | 对应口播文本相似度中位 {np.median(ts):.2f}")
        for lo, hi in ((0.5, 0.7), (0.7, 0.85), (0.85, 1.01)):
            m = (ss >= lo) & (ss < hi)
            if m.any():
                print(f"  指纹 {lo:.2f}-{hi:.2f}: {m.sum():4d} 对，文本相似度中位 {np.median(ts[m]):.2f}，"
                      f"≥0.85 占 {(ts[m] >= 0.85).mean():.0%}")
        for p in pairs[:5]:
            print(f'  {p[0]:.2f}/{p[1]:.2f}  {p[2][:34]}  ≈  {p[3][:34]}')


if __name__ == "__main__":
    main()
