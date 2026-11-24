# -*- coding: utf-8 -*-
"""估算这批新增要跑多少条转录：有音轨数、音频时长、按形态预估有口播数。"""
import csv, json, glob
from collections import Counter, defaultdict

CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
PROBE = r"E:\video-download\analysis\data_20261123\probe.csv"
WL = r"E:\video-download\analysis\data_20261123\wl_20261123.json"
LAB = r"E:\video-download\analysis\data_20261123\labels"

# 11-16 那批实测的「形态 → 有口播率」
RATE = {"真人单人出镜": 0.94, "真人多人剧情": 0.90, "手机屏幕录屏UGC": 0.88,
        "直播切片": 0.87, "AI生成动画": 0.88, "图文卡点": 0.71, "游戏界面演示": 0.85}

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
probe = {r["file"]: r for r in csv.DictReader(open(PROBE, encoding="utf-8-sig"))}
wl = {it["idx"]: it for it in json.load(open(WL, encoding="utf-8"))["items"]}
lab = {}
for f in glob.glob(LAB + r"\labels_b*.json"):
    for r in json.load(open(f, encoding="utf-8-sig"))["labels"]:
        lab[int(r["idx"])] = r

n = len(rows)
audio = sum(1 for r in rows if str(probe.get(r["file"], {}).get("has_audio", "")).strip() in ("1", "1.0"))
dur = sum(float(r["duration"]) for r in rows)
print(f"新增 {n} 条 | 有音轨 {audio} 条（{audio/n:.0%}）| 总时长 {dur/60:.0f} 分钟")

# 按形态估
cnt = Counter()
est = 0.0
dmin = defaultdict(float)
for i, it in enumerate(wl.values()):
    r = rows[i]
    fmt = lab[i]["fmt"]
    cnt[fmt] += 1
    dmin[fmt] += float(r["duration"]) / 60
    if str(probe.get(r["file"], {}).get("has_audio", "")).strip() in ("1", "1.0"):
        est += RATE.get(fmt, 0.8)

print(f"\n按形态（有音轨的条数 × 11-16 实测有口播率）预估有口播 ≈ {est:.0f} 条（{est/n:.0%}）")
print(f"{'形态':<16}{'条数':>6}{'音频min':>9}{'预估有口播':>10}")
for k, v in cnt.most_common():
    print(f"{k:<16}{v:>6}{dmin[k]:>9.0f}{v*RATE.get(k,0.8):>10.0f}")

# 有声但可能只是 BGM：用 rhythm 的 speech_mod / silence 粗看
rh = {}
if True:
    p = r"E:\video-download\analysis\data_20261123\rhythm.json"
    try:
        d = json.load(open(p, encoding="utf-8"))
        rh = {x["file"]: x for x in (d if isinstance(d, list) else d.get("rows", []))}
    except Exception as e:
        print("rhythm 读取失败:", e)

if rh:
    sp = [rh[r["file"]].get("speech_mod") for r in rows if r["file"] in rh]
    sp = [x for x in sp if isinstance(x, (int, float))]
    sp.sort()
    if sp:
        print(f"\nspeech_mod 分布 p25/p50/p75/p90: {sp[len(sp)//4]:.2f} / {sp[len(sp)//2]:.2f} / {sp[3*len(sp)//4]:.2f} / {sp[int(len(sp)*0.9)]:.2f}")
