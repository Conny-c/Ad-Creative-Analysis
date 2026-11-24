# -*- coding: utf-8 -*-
"""L1: 每素材一张 6 帧接触印相。按内容自动裁黑边 + 自适应行高拼图。"""
import csv, subprocess, tempfile, re, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(os.environ.get("SUGO_WORK", str(Path(__file__).resolve().parent.parent)))
SHEETS = Path(os.environ.get("SUGO_SHEET_DIR", str(ROOT / "assets" / "sheets")))
TMP = Path(os.environ.get("SUGO_TMP_DIR", str(ROOT / "assets" / "_tmp")))
FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"
CW, MAXH, CAP = 400, 714, 20
CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def times(dur):
    d = max(float(dur or 0), 0.5)
    if d < 4.5:
        return [round(d * f, 2) for f in (0.08, 0.25, 0.45, 0.62, 0.8, 0.95)]
    return [0.4, 1.2, 2.4, round(d * 0.35, 2), round(d * 0.65, 2), round(d * 0.95, 2)]


def detect_crop(src, dur, w, h):
    """黑边检测，返回 crop=w:h:x:y 字符串；无黑边返回 None"""
    t = min(max(dur * 0.1, 0.5), 5)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "info", "-ss", f"{t:.2f}", "-t", "4",
           "-i", str(src), "-vf", "cropdetect=24:2:0", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True)
    found = CROP_RE.findall((r.stderr or b"").decode("utf-8", "replace"))
    if not found:
        return None
    cw, ch, cx, cy = (int(v) for v in found[-1])
    if cw < w * 0.5 or ch < h * 0.5:
        return None
    if cw >= w * 0.98 and ch >= h * 0.98:
        return None
    return f"crop={cw}:{ch}:{cx}:{cy}"


def grab(src, t, dst, crop):
    vf = (crop + "," if crop else "") + \
         f"scale={CW}:{MAXH}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", vf, str(dst)]
    subprocess.run(cmd, capture_output=True)
    return dst.exists() and dst.stat().st_size > 1000


def build(row):
    src = Path(row["path"])
    out = SHEETS / (src.stem + ".jpg")
    if out.exists() and out.stat().st_size > 8000:
        return out.name, "skip"
    crop = detect_crop(src, float(row["duration"]), int(row["w"]), int(row["h"]))
    tiles = []
    with tempfile.TemporaryDirectory(dir=TMP, ignore_cleanup_errors=True) as td:
        for i, t in enumerate(times(row["duration"])):
            p = Path(td) / f"f{i}.png"
            if grab(src, t, p, crop):
                tiles.append((t, Image.open(p).convert("RGB").copy()))
        if not tiles:
            return out.name, "FAIL no frame"
        rows = [tiles[i:i + 3] for i in range(0, len(tiles), 3)]
        heights = [max(im.height for _, im in r) + CAP for r in rows]
        canvas = Image.new("RGB", (CW * 3, sum(heights)), (12, 12, 12))
        d = ImageDraw.Draw(canvas)
        y = 0
        for r, rh in zip(rows, heights):
            for j, (t, im) in enumerate(r):
                x = j * CW + (CW - im.width) // 2
                canvas.paste(im, (x, y))
                d.text((j * CW + 6, y + rh - CAP + 3), f"{t:.1f}s", fill=(235, 235, 90))
            y += rh
        canvas.save(out, "JPEG", quality=88)
    return out.name, "ok"


def main():
    SHEETS.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(Path(os.environ.get("SUGO_DATA_DIR", str(ROOT / "data"))) / "probe.csv", encoding="utf-8-sig")))
    print("videos:", len(rows), flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(build, rows))
    print("built:", sum(1 for r in res if r[1] == "ok"),
          "skipped:", sum(1 for r in res if r[1] == "skip"),
          "failed:", sum(1 for r in res if r[1].startswith("FAIL")))
    for r in res:
        if r[1].startswith("FAIL"):
            print("BAD", r)


if __name__ == "__main__":
    main()
