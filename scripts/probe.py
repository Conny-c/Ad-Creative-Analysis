# -*- coding: utf-8 -*-
"""L0: 视频技术元数据 + 剪辑节奏（场景切换）抽取"""
import json, subprocess, hashlib, csv, os, sys, re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(os.environ.get("SUGO_VIDEO_DIR", r"E:\video-download\2026-10-19\Sugo"))
OUT = Path(os.environ.get("SUGO_DATA_DIR",
                          str(Path(__file__).resolve().parent.parent / "data")))
FOLDERS = [x for x in os.environ.get("SUGO_FOLDERS", "").split(";") if x.strip()]
FFPROBE = r"C:\ffmpeg\bin\ffprobe.exe"
FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(p):
    cmd = [FFPROBE, "-v", "error", "-show_format", "-show_streams",
           "-of", "json", str(p)]
    j = json.loads(subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8", "replace"))
    fmt = j.get("format", {})
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video"]
    as_ = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]
    v = vs[0] if vs else {}
    fps = 0.0
    try:
        n, d = v.get("avg_frame_rate", "0/1").split("/")
        fps = round(float(n) / float(d), 2) if float(d) else 0.0
    except Exception:
        pass
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    dur = float(fmt.get("duration") or v.get("duration") or 0)
    return {
        "duration": round(dur, 2), "w": w, "h": h,
        "ratio": round(w / h, 3) if h else 0,
        "fps": fps,
        "vcodec": v.get("codec_name", ""),
        "vbr_kbps": round(int(fmt.get("bit_rate") or 0) / 1000),
        "acodec": (as_[0].get("codec_name", "") if as_ else ""),
        "achannels": (as_[0].get("channels", 0) if as_ else 0),
        "has_audio": 1 if as_ else 0,
        "size_mb": round(int(fmt.get("size") or 0) / 1048576, 2),
        "pix_fmt": v.get("pix_fmt", ""),
    }


SCENE_RE = re.compile(r"pts_time:([0-9.]+)")


def cuts(p, dur):
    """场景切换时间点（阈值 0.3，先降到 320 宽提速）"""
    cmd = [FFMPEG, "-hide_banner", "-nostats", "-i", str(p), "-an",
           "-vf", r"scale=320:-2,select='gt(scene,0.3)',metadata=print",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True)
    txt = (r.stderr or b"").decode("utf-8", "replace")
    ts = [float(x) for x in SCENE_RE.findall(txt)]
    ts = [t for t in ts if 0 < t < max(dur - 0.05, 0.1)]
    return ts


def one(p):
    row = {"file": p.name, "stem": p.stem, "path": str(p)}
    try:
        row.update(probe(p))
    except Exception as e:
        row.update({"duration": 0, "error": f"probe:{e}"})
        return row
    try:
        ts = cuts(p, row["duration"])
    except Exception as e:
        ts = []
        row["error"] = f"cuts:{e}"
    row["cuts"] = len(ts)
    row["cut_times"] = ";".join(f"{t:.2f}" for t in ts)
    d = row["duration"] or 1
    row["cuts_per_10s"] = round(len(ts) / d * 10, 2)
    row["first_cut"] = round(ts[0], 2) if ts else ""
    row["hook_cuts_3s"] = sum(1 for t in ts if t <= 3)
    row["shot_len_avg"] = round(d / (len(ts) + 1), 2)
    try:
        row["md5"] = md5(p)
    except Exception as e:
        row["md5"] = ""
        row["error"] = f"md5:{e}"
    # 来源/地区来自文件名
    parts = p.stem.split("_")
    row["competitor"] = parts[0] if parts else ""
    row["source"] = parts[1] if len(parts) > 1 else ""
    row["region"] = parts[2] if len(parts) > 2 else ""
    row["folder"] = p.parent.name
    row["product"] = re.sub(r"\(\d+\)$", "", p.parent.name)
    return row


def main():
    files = sorted([p for p in ROOT.rglob("*")
                    if p.suffix.lower() in (".mp4", ".webm", ".mov")])
    if FOLDERS:
        files = [p for p in files if p.parent.name in FOLDERS]
    print(f"files: {len(files)}", flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, files))
    OUT.mkdir(parents=True, exist_ok=True)
    keys = ["product", "folder", "competitor", "source", "region", "file", "stem", "duration", "w", "h", "ratio",
            "fps", "vcodec", "pix_fmt", "vbr_kbps", "size_mb", "has_audio", "acodec",
            "achannels", "cuts", "cuts_per_10s", "hook_cuts_3s", "first_cut", "shot_len_avg",
            "cut_times", "md5", "path", "error"]
    with open(OUT / "probe.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", OUT / "probe.csv", flush=True)


if __name__ == "__main__":
    main()
