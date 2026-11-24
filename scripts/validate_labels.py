# -*- coding: utf-8 -*-
"""打标结果自检：覆盖、对齐、枚举合法性、空值。"""
import glob, json, re
from collections import Counter

WL = r"E:\video-download\analysis\data_20261123\wl_20261123.json"
LAB = r"E:\video-download\analysis\data_20261123\labels"

ENUM = {
    "fmt": {"真人单人出镜", "真人多人剧情", "手机屏幕录屏UGC", "图文卡点", "游戏界面演示", "直播切片", "AI生成动画"},
    "pop": {"年轻女性", "年轻男性", "男女双人", "多人", "无真人"},
    "lang": {"英语", "菲律宾语", "印尼语", "越南语", "泰语", "马来语", "西班牙语", "葡萄牙语", "法语",
             "德语", "土耳其语", "阿拉伯语", "日语", "韩语", "中文", "俄语", "印地语", "无字幕", "多语混合"},
    "hook": {"真人开场直说", "利益收益展示", "悬念提问", "冲突剧情", "产品界面直接开场", "颜值身材吸引",
             "纯文字提问", "素人自拍"},
    "prod": {"前3秒", "3-10秒", "10秒后", "无产品界面"},
    "cta": {"品牌logo收尾", "下载安装引导", "立即开聊引导", "充值送礼引导", "无明确CTA"},
    "grade": {"实拍精制", "实拍粗糙UGC", "纯UI加文字", "录屏拼接"},
    "selling": {"交友聊天", "直播打赏", "语音房派对", "游戏互动", "赚钱福利", "附近的人", "视频匹配", "其他"},
}

wl = {it["idx"]: it for it in json.loads(open(WL, encoding="utf-8").read())["items"]}
lab = {}
for f in sorted(glob.glob(LAB + r"\labels_b*.json")):
    for r in json.load(open(f, encoding="utf-8-sig"))["labels"]:
        lab[int(r["idx"])] = r

miss = [i for i in wl if i not in lab]
extra = [i for i in lab if i not in wl]
print(f"worklist {len(wl)} | 打标 {len(lab)} | 缺 {len(miss)} | 多 {len(extra)}")
if miss:
    print("  缺:", miss[:20])

bad_file = [i for i, r in lab.items() if r.get("file") != wl[i]["file"]]
print("file 对不上的:", len(bad_file), bad_file[:5])

viol = Counter()
for r in lab.values():
    for k, ok in ENUM.items():
        if r.get(k) not in ok:
            viol[(k, r.get(k))] += 1
print("枚举越界:", sum(viol.values()))
for k, v in viol.most_common(10):
    print("   ", k, v)

print("缺 summary:", sum(1 for r in lab.values() if not (r.get("summary") or "").strip()))
print("summary>40字:", sum(1 for r in lab.values() if len(r.get("summary") or "") > 40))
print("conf 分布:", Counter(str(r.get("conf")) for r in lab.values()).most_common())
print("fmt:", Counter(r["fmt"] for r in lab.values()).most_common())
print("selling:", Counter(r["selling"] for r in lab.values()).most_common())
print("有 text 的:", sum(1 for r in lab.values() if (r.get("text") or "").strip()))
