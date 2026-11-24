# -*- coding: utf-8 -*-
"""周更：给定期号，自动跑 L0/L1（元数据 / 抽帧 / 节奏），并与历史台账做差集

用法：
    python tools/weekly.py --date 20261026
    python tools/weekly.py --date 20261026 --root "E:\\video-download" --work "D:\\deepseek harness\\video-analysis"

产出：
    data_<期号>\\probe.csv, rhythm.json      本期技术指标
    assets\\sheets_<期号>\\*.jpg              本期接触印相（供视觉打标）
    out\\weekly_<期号>_新增.csv              本期新增素材清单（待打标）
    out\\master_ledger.csv                   累积台账（md5 去重）
"""
import argparse, csv, os, subprocess, sys
from pathlib import Path
import pandas as pd

TOOLS = Path(__file__).resolve().parent
PY = sys.executable


def run(script, env):
    print(f"--- {script} ---", flush=True)
    r = subprocess.run([PY, str(TOOLS / script)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        print("   ", line)
    if r.returncode != 0:
        print((r.stderr or "")[-1500:])
        raise SystemExit(f"{script} failed: {r.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="期号，如 20261026")
    ap.add_argument("--root", default=r"E:\video-download")
    ap.add_argument("--work", default=str(TOOLS.parent))
    ap.add_argument("--competitor", default="", help="单个竞品名，如 Sugo")
    ap.add_argument("--competitors", default="", help="多个竞品，分号分隔，如 Sugo;Tango")
    ap.add_argument("--top5", action="store_true", help="按本期素材量自动取前 5")
    ap.add_argument("--all", action="store_true", help="本期全部竞品")
    args = ap.parse_args()

    work = Path(args.work)
    d = args.date
    dashed = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    period = Path(args.root) / dashed
    if not period.exists():
        raise SystemExit(f"找不到期号目录：{period}")

    # 该期所有含视频的子文件夹
    folders = [p.name for p in period.iterdir()
               if p.is_dir() and any(f.suffix.lower() in (".mp4", ".webm", ".mov") for f in p.iterdir() if f.is_file())]
    if args.competitor:
        sel = [args.competitor]
    elif args.competitors:
        sel = [x.strip() for x in args.competitors.split(";") if x.strip()]
    elif args.top5:
        def cnt(n):
            return sum(1 for f in (period / n).rglob("*") if f.suffix.lower() in (".mp4", ".webm", ".mov"))
        sel = sorted(folders, key=cnt, reverse=True)[:5]
    elif args.all:
        sel = folders
    else:
        sel = ["Sugo"]
    missing = [s for s in sel if s not in folders]
    if missing:
        raise SystemExit(f"这些竞品本期没有素材：{missing}\n可选：{folders}")
    print(f"期号 {d}｜竞品 {len(sel)} 个：{'; '.join(sel)}", flush=True)

    data_dir = work / f"data_{d}"
    sheet_dir = work / "assets" / f"sheets_{d}"
    data_dir.mkdir(parents=True, exist_ok=True)
    sheet_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["SUGO_WORK"] = str(work)
    env["SUGO_VIDEO_DIR"] = str(period)
    env["SUGO_FOLDERS"] = ";".join(sel)
    env["SUGO_DATA_DIR"] = str(data_dir)
    env["SUGO_SHEET_DIR"] = str(sheet_dir)

    run("probe.py", env)
    run("sheets.py", env)
    run("rhythm.py", env)
    run("ai_detect.py", env)
    run("ai_candidates.py", env)

    probe = pd.read_csv(data_dir / "probe.csv")
    rhythm = pd.read_json(data_dir / "rhythm.json") if (data_dir / "rhythm.json").exists() else pd.DataFrame()
    if len(rhythm):
        probe = probe.merge(rhythm, on="file", how="left")

    master_path = work / "out" / "master_ledger.csv"
    work.joinpath("out").mkdir(parents=True, exist_ok=True)
    if master_path.exists():
        master = pd.read_csv(master_path)
    else:
        seed = work / "out" / "ledger.csv"
        master = pd.read_csv(seed) if seed.exists() else pd.DataFrame()
        if len(master):
            master["期号"] = "20261019"
    known = set(master.md5.dropna()) if "md5" in master else set()
    new = probe[~probe.md5.isin(known)].copy()
    new["期号"] = d
    new["sheet"] = new.file.map(lambda f: str(sheet_dir) + "\\" + Path(f).stem + ".jpg")
    print(f"\n本期 {len(probe)} 条，新增 {len(new)} 条，历史 {len(master)} 条")

    out_csv = work / "out" / f"weekly_{d}_新增.csv"
    new.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # 只把技术字段并入 master（视觉标签下一轮补）
    base_cols = [c for c in master.columns if c in new.columns] if len(master) else list(new.columns)
    merged = pd.concat([master[base_cols] if len(master) else master, new[base_cols]], ignore_index=True)
    merged.to_csv(master_path, index=False, encoding="utf-8-sig")

    if len(new):
        print("\n新增素材结构速览：")
        print(new.groupby(["source", "region"]).size().to_string())
        print("时长中位 %.1fs / 平均镜头 %.1fs / 方横屏 %d 条"
              % (new.duration.median(), new.shot_avg.median() if "shot_avg" in new else -1,
                 int((new.h > new.w * 1.2).eq(False).sum())))
    print(f"\n待办：把 {out_csv} 里的 sheet 列交给模型按 analysis/label_guide_v2.md 打标，再跑 merge_multi.py + build_library_xlsx.py")


if __name__ == "__main__":
    main()
