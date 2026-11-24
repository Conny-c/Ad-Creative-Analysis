# -*- coding: utf-8 -*-
"""AI 视觉复核候选清单：从全量里挑出"值得人/模型看一眼"的素材

排序依据（可解释）：
    +5  C2PA 凭证确认（必须复核，用于校准）
    +3  形态 = AI生成动画
    +2  无真人（纯 UI / 动画更容易是合成）
    +1  平台 AIGC 标记
    +1  时长 ≤20s 且是整数秒（AI 工具常见 4/5/8/10/15s 定长输出）
    +1  画幅非标准竖屏

输出 data/ai_visual_worklist.json（供模型按 label_guide_ai.md 判「AI/实拍/拿不准 + 证据」）
"""
import csv, json, os
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get("SUGO_WORK", str(Path(__file__).resolve().parent.parent)))
DATA = Path(os.environ.get("SUGO_DATA_DIR", str(ROOT / "data")))


def main(cap=400):
    probe = pd.read_csv(DATA / "probe.csv")
    ai = pd.read_csv(DATA / "ai_signals.csv")[["file", "ai_flag", "c2pa_generator", "evidence"]]
    df = probe.merge(ai, on="file", how="left")

    ledger = None
    for name in ("ledger_full.csv", "ledger_all.csv"):
        p = ROOT / "out" / name
        if p.exists():
            ledger = pd.read_csv(p)
            break
    if ledger is not None:
        cols = [c for c in ("file", "fmt", "pop", "duration") if c in ledger.columns]
        df = df.merge(ledger[cols].rename(columns={"duration": "ledger_duration"}), on="file", how="left")
    else:
        df["fmt"] = ""
        df["pop"] = ""

    def score(r):
        s, why = 0, []
        if r.get("ai_flag") == "凭证确认":
            s += 5; why.append("凭证确认")
        if r.get("fmt") == "AI生成动画":
            s += 3; why.append("AI动画")
        if r.get("pop") == "无真人":
            s += 1; why.append("无真人")
        if r.get("ai_flag") == "平台AIGC标记":
            s += 2; why.append("平台标记")
        d = float(r.get("duration") or 0)
        if d and d <= 20 and abs(d - round(d)) <= 0.15:
            s += 0.5; why.append("整数秒")
        w, h = int(r.get("w") or 0), int(r.get("h") or 0)
        if not (h > w * 1.2):
            s += 0.5; why.append("非竖屏")
        return s, "+".join(why)

    df[["score", "reason"]] = df.apply(lambda r: pd.Series(score(r)), axis=1)
    df = df.sort_values(["score", "duration"], ascending=[False, True])
    pick = df[df.score >= 2].head(cap)

    rows = []
    for i, r in enumerate(pick.itertuples(index=False), 1):
        rows.append({
            "idx": i, "file": r.file, "product": r.product,
            "sheet": f"assets/sheets/{Path(r.file).stem}.jpg",
            "duration": float(r.duration), "w": int(r.w), "h": int(r.h),
            "fmt": getattr(r, "fmt", "") if isinstance(getattr(r, "fmt", ""), str) else "",
            "ai_flag": r.ai_flag if isinstance(r.ai_flag, str) else "",
            "score": int(r.score), "reason": r.reason,
        })
    out = DATA / "ai_visual_worklist.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"候选 {len(rows)} / {len(df)} 条（score>=2，上限 {cap}）")
    print(pd.Series([r["reason"] for r in rows]).value_counts().head(8).to_string())
    print("含凭证确认:", sum(1 for r in rows if r["ai_flag"] == "凭证确认"))
    print("wrote", out)


if __name__ == "__main__":
    main()
