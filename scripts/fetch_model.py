# -*- coding: utf-8 -*-
"""把 faster-whisper 模型直接下到工作区（不依赖 HF 缓存，避免沙箱只读）。

用法:
  python fetch_model.py Systran/faster-whisper-medium E:\\video-download\\analysis\\models\\medium
"""
import json, os, sys, time, urllib.request
from pathlib import Path

repo = sys.argv[1]
dest = Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)

api = f"https://huggingface.co/api/models/{repo}"
info = json.loads(urllib.request.urlopen(api, timeout=60).read())
files = [s["rfilename"] for s in info.get("siblings", []) if not s["rfilename"].endswith(".md")]
print("files:", files, flush=True)

for fn in files:
    out = dest / fn
    if out.exists() and out.stat().st_size > 0:
        print(f"skip {fn} ({out.stat().st_size/1048576:.1f} MB)", flush=True)
        continue
    url = f"https://huggingface.co/{repo}/resolve/main/{fn}"
    tmp = out.with_suffix(out.suffix + ".part")
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total and done % (8 << 20) < (1 << 20):
                el = max(time.time() - t0, 1e-6)
                print(f"  {fn} {done/1048576:.0f}/{total/1048576:.0f} MB "
                      f"{done/1048576/el:.1f} MB/s", flush=True)
    tmp.replace(out)
    print(f"ok {fn} {out.stat().st_size/1048576:.1f} MB in {time.time()-t0:.1f}s", flush=True)

print("DONE", dest, flush=True)
