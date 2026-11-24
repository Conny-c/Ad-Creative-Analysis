# -*- coding: utf-8 -*-
"""导出待翻译口播（按 norm 去重）+ 把译文合回 per-key 的 vo_zh.json。

    python dump_vo_texts.py                 # 导出
       -> data_20261116/vo_index.json   {sid: {lang, text, keys, products, n}}
       -> data_20261116/vo_batch.txt     sid<TAB>lang<TAB>text  （给人/模型读）
    python dump_vo_texts.py --merge         # 合并
       <- data_20261116/vo_zh_idx.json   {"sid": "中文"}   翻译结果
       -> data_20261116/vo_zh.json       {"product|stem": "中文"}
"""
import argparse, hashlib, json, re
from collections import defaultdict
from pathlib import Path

D = Path(r"E:\video-download\analysis\data_20261116")


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def export():
    asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
    cls = json.loads((D / "vo_class.json").read_text(encoding="utf-8"))
    groups = defaultdict(lambda: dict(keys=[], lang="", text="", dur=0.0))
    for k, v in asr.items():
        if (cls.get(k) or {}).get("cls") != "vo":
            continue
        n = norm(v.get("text"))
        if not n:
            continue
        g = groups[n]
        g["keys"].append(k)
        g["lang"] = g["lang"] or v.get("lang")
        g["text"] = v.get("text")
        g["dur"] = max(g["dur"], v.get("dur") or 0)

    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]["keys"]), kv[1]["lang"]))
    index, lines = {}, []
    for n, (key_norm, g) in enumerate(ordered, 1):
        # sid 用 norm 文本的哈希，增删条目也不会变，可增量翻译
        sid = hashlib.md5(key_norm.encode("utf-8")).hexdigest()[:10]
        index[sid] = dict(lang=g["lang"], text=g["text"], keys=g["keys"],
                          n=len(g["keys"]),
                          products=sorted({k.split("|")[0] for k in g["keys"]}))
        lines.append(f'{sid}\t{g["lang"]}\t{g["text"]}')
    (D / "vo_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    (D / "vo_batch.txt").write_text("\n".join(lines), encoding="utf-8")
    tot = sum(v["n"] for v in index.values())
    print(f"真口播 {tot} 条 -> 去重 {len(index)} 段 | 字符 {sum(len(v['text']) for v in index.values()):,}")
    from collections import Counter
    print("语种:", Counter(v["lang"] for v in index.values()).most_common())


def merge():
    index = json.loads((D / "vo_index.json").read_text(encoding="utf-8"))
    tr = {}
    for f in sorted(D.glob("vo_zh_p*.json")) + ([D / "vo_zh_idx.json"] if (D / "vo_zh_idx.json").exists() else []):
        tr.update(json.loads(Path(f).read_text(encoding="utf-8")))
    # 近似文案复用：ASR 噪声导致同一句口播有多个变体，相似度够高就沿用已译
    import difflib
    done = [(sid, g["text"]) for sid, g in index.items() if sid in tr]
    reuse = 0
    for sid, g in index.items():
        if sid in tr or not done:
            continue
        best, score = None, 0.0
        for tsid, ttext in done:
            s = difflib.SequenceMatcher(None, g["text"][:260], ttext[:260]).quick_ratio()
            if s > score:
                best, score = tsid, s
        if score >= 0.93:
            tr[sid] = tr[best]
            reuse += 1
    out, miss = {}, []
    for sid, g in index.items():
        zh = tr.get(sid, "").strip()
        if not zh:
            miss.append(sid)
            continue
        for k in g["keys"]:
            out[k] = zh
    (D / "vo_zh.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"合并 {len(out)} 条 per-key 译文；原文段 {len(index)}，已译 {len(index)-len(miss)}")
    if miss:
        print("未译 sid:", ",".join(miss[:40]), "..." if len(miss) > 40 else "")


def todo(threshold=0.93):
    import difflib
    index = json.loads((D / "vo_index.json").read_text(encoding="utf-8"))
    tr = {}
    for f in sorted(D.glob("vo_zh_p*.json")):
        tr.update(json.loads(Path(f).read_text(encoding="utf-8")))
    done = [(s, index[s]["text"]) for s in index if s in tr]
    keep = []
    for s in index:
        if s in tr:
            continue
        t = index[s]["text"]
        best = max((difflib.SequenceMatcher(None, t[:260], dt[:260]).quick_ratio(), ds)
                   for ds, dt in done) if done else (0.0, None)
        if best[0] < threshold:
            keep.append(s)
    lines = [f'{s}\t{index[s]["lang"]}\t{index[s]["text"]}' for s in keep]
    (D / "vo_todo.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"真正待译 {len(keep)} / 共 {len(index)}（近似复用已去重）")
    for l in lines:
        print(l[:240])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--todo", action="store_true")
    a = ap.parse_args()
    merge() if a.merge else (todo() if a.todo else export())



