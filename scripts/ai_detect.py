# -*- coding: utf-8 -*-
"""AI 生成信号检测（凭证优先，不做无根据的视觉断言）

输出 data/ai_signals.csv，字段：
    file, product, c2pa, c2pa_source_type, c2pa_generator, c2pa_signer,
    aigc_tag, aigc_label_type, encoder, ai_flag, evidence

ai_flag 四档：
    凭证确认      —— C2PA 里 digitalSourceType 命中 trainedAlgorithmicMedia（平台/工具自证 AI 生成或合成）
    凭证-其他     —— 有 C2PA 但没有 AI 声明（设备拍摄、平台转码等）
    平台AIGC标记  —— 仅 aigc_info 字段（抖音/TikTok 导出标记），不能定案
    未见信号      —— 都没有

用法：
    python tools/ai_detect.py                     # 用 data/probe.csv
    SUGO_DATA_DIR=... python tools/ai_detect.py   # 周更时由 weekly.py 调用
"""
import csv, json, os, re, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(os.environ.get("SUGO_WORK", str(Path(__file__).resolve().parent.parent)))
DATA = Path(os.environ.get("SUGO_DATA_DIR", str(ROOT / "data")))
FFPROBE = r"C:\ffmpeg\bin\ffprobe.exe"

# 只有在 JUMBF/C2PA 结构里出现才算数，避免二进制随机字节误命中
SRC_TYPE_RE = re.compile(rb"digitalsourcetype/([A-Za-z]{6,60})")
SRC_TYPES = ["compositeWithTrainedAlgorithmicMedia","trainedAlgorithmicMedia","compositeSynthetic","algorithmicMedia","compositeCapture","digitalCapture","virtualRecording","dataDrivenMedia","compositeWithTrainedAlgorithmicMedia"]
MAIL_RE = re.compile(rb"[a-z0-9._%+-]{2,30}@[a-z0-9.-]{3,40}\.[a-z]{2,6}", re.I)
PUB_RE = re.compile(rb"([A-Za-z0-9][A-Za-z0-9 .,&'\x2d]{2,48})")
WINDOW_BACK, WINDOW_FWD = 8192, 196608


NOISE = {"dname", "xname", "tname", "mname", "jumd", "json", "cbor", "name", "uuid", "label"}

# 转码器签名：说明这条只是被转码工具重新封装过，不代表内容由 AI 生成，需要看图复核
TRANSCODE_RE = re.compile(r"transcod|media transcode|ffmpeg|x264|handbrake", re.I)


def find_generator(seg: bytes) -> str:
    """claim_generator_info 后是 CBOR map（a4 dname x1a 'TIKTOK AD Creative Toolbox'），
    跳过 box 头，从第一个大写字母开始读工具名。"""
    best = ""
    for m in re.finditer(rb"claim_generator_info", seg):
        tail = seg[m.end(): m.end() + 120]
        st = next((i for i, c in enumerate(tail) if 65 <= c <= 90), None)
        if st is None:
            continue
        run = PUB_RE.match(tail[st:])
        if not run:
            continue
        cand = run.group(1).decode("ascii", "ignore")
        for stop in ("gversion", "specVersion", "gspecVersion", "version", "org"):
            cand = cand.split(stop)[0]
        cand = cand.strip(" .&'-")
        low = cand.lower()
        if len(cand) < 6 or low in NOISE or "claim" in low or "info" in low:
            continue
        score = (2 if " " in cand else 0) + (1 if any(c.isupper() for c in cand) else 0) + len(cand) / 100
        if score > 0.5 and len(cand) > len(best):
            best = cand[:60]
    return best


def c2pa_of(path: Path):
    """返回 (是否命中, source_type, generator, signer)"""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(524288)
            if b"c2pa" not in head.lower():
                # moov 常在尾部
                if size > 524288:
                    f.seek(max(0, size - 524288))
                    if b"c2pa" not in f.read().lower():
                        return False, "", "", ""
            f.seek(0)
            blob = f.read(min(size, 8 * 1024 * 1024))
    except Exception:
        return False, "", "", ""

    idx = -1
    while True:
        idx = blob.lower().find(b"c2pa", idx + 1)
        if idx < 0:
            return False, "", "", ""
        seg = blob[max(0, idx - WINDOW_BACK): idx + WINDOW_FWD]
        # 必须有 JUMBF 结构或 claim 描述，否则视为噪声
        if b"jumd" not in seg and b"c2pa.claim" not in seg:
            continue
        m = SRC_TYPE_RE.search(seg)
        source_type = ""
        if m:
            raw = m.group(1).decode("ascii", "ignore")
            for t in SRC_TYPES:
                if raw.startswith(t):
                    source_type = t
                    break
            else:
                source_type = raw[:40]
        generator = find_generator(seg)
        mail = MAIL_RE.search(seg)
        signer = mail.group(0).decode("ascii", "ignore") if mail else ""
        return True, source_type, generator, signer


def probe_tags(path: Path):
    tags = {}
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                           capture_output=True)
        j = json.loads(r.stdout.decode("utf-8", "replace"))
        for src in [j.get("format", {})] + j.get("streams", []):
            for k, v in (src.get("tags") or {}).items():
                tags[k.lower()] = str(v)
    except Exception:
        pass
    return tags


def one(row):
    p = Path(row["path"])
    tags = probe_tags(p)
    hit, stype, gen, signer = c2pa_of(p)
    aigc = tags.get("aigc_info", "")
    label_type = ""
    if aigc:
        m = re.search(r'"aigc_label_type"\s*:\s*(\d+)', aigc)
        label_type = m.group(1) if m else ""

    ev = []
    if hit:
        ev.append(f"c2pa:{stype or 'present'}")
        if gen:
            ev.append(f"gen:{gen}")
        if signer:
            ev.append(f"sign:{signer}")
    if aigc:
        ev.append(f"aigc_info:{label_type or 'yes'}")

    if hit and "trainedalgorithmicmedia" in stype.lower():
        flag = "凭证确认"
    elif hit:
        flag = "凭证-其他"
    elif aigc:
        flag = "平台AIGC标记"
    else:
        flag = "未见信号"

    return {
        "file": row["file"], "product": row["product"], "path": str(p),
        "c2pa": int(hit), "c2pa_source_type": stype, "c2pa_generator": gen, "c2pa_signer": signer,
        "aigc_tag": aigc, "aigc_label_type": label_type,
        "encoder": tags.get("encoder", ""), "ai_flag": flag, "evidence": ";".join(ev),
        "ai_note": ("转码器签名，需看图确认" if (flag == "凭证确认" and gen and TRANSCODE_RE.search(gen)) else ""),
    }


def main():
    probe = list(csv.DictReader(open(DATA / "probe.csv", encoding="utf-8-sig")))
    print(f"files: {len(probe)}", flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(one, probe))
    out = DATA / "ai_signals.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    c = Counter(r["ai_flag"] for r in rows)
    print("ai_flag:", dict(c))
    for r in rows:
        if r["ai_flag"] == "凭证确认":
            print("  确认AI:", r["product"], "|", r["file"][:52], "|", r["c2pa_generator"] or "-")
    print("wrote", out)


if __name__ == "__main__":
    main()
