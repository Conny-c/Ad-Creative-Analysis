# -*- coding: utf-8 -*-
"""1123 期口播工作簿：1530 条全部入表，其中 1316 条是实转，214 条继承代表条。

    python build_vo_1123.py

页签：1_口播总表 / 2_口播库 / 3_无人声清单 / 4_统计 / 5_口播vs花字
"""
import csv, json, math, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

D = Path(r"E:\video-download\analysis\data_20261123")
CSV = r"E:\video-download\analysis\out\weekly_20261123_新增.csv"
XLSX_OUT = r"E:\video-download\analysis\out\2026-11-23_口播转录表.xlsx"
XLSX_LAB = r"E:\video-download\analysis\out\2026-11-23_竞品素材拆解表.xlsx"
ZH_DIR = D / "zh"

HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=10)
VO_FILL = PatternFill("solid", fgColor="E2EFDA")
NONE_FILL = PatternFill("solid", fgColor="FCE4D6")
LYRIC_FILL = PatternFill("solid", fgColor="FFF2CC")
LABEL = {"vo": "有口播", "none": "无人声", "lyric": "歌词(非文案)",
         "credit": "幻觉/署名", "error": "报错", "未跑": "未跑"}


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def wlen(s):
    s = str(s or "")
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def write_sheet(ws, head, rows, widths, wrap_cols=()):
    ws.append(head)
    for c in range(1, len(head) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(list(r))
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(head)):
        lines = 1
        for c in row:
            wrap = c.column - 1 in wrap_cols
            c.alignment = Alignment(vertical="top", wrap_text=wrap)
            c.font = Font(size=9)
            if wrap:
                lines = max(lines, math.ceil(wlen(c.value) / max(widths[c.column - 1] - 1, 4)))
        ws.row_dimensions[row[0].row].height = min(13.5 * max(lines, 1) + 3, 170)


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    asr = json.loads((D / "asr.json").read_text(encoding="utf-8"))
    cls = json.loads((D / "vo_class.json").read_text(encoding="utf-8"))
    dmap = json.loads((D / "dedupe_map.json").read_text(encoding="utf-8"))
    skip = dmap.get("skip_map", {})

    zh_rid = {}
    for f in sorted(ZH_DIR.glob("zh_b*.json")):
        zh_rid.update(json.loads(f.read_text(encoding="utf-8-sig")))
    uni = json.loads((D / "vo_unique.json").read_text(encoding="utf-8"))
    rid2keys = {str(u["rid"]): u["keys"] for u in uni}
    zh_key = {}
    for rid, keys in rid2keys.items():
        t = zh_rid.get(rid, "")
        for k in keys:
            zh_key[k] = t

    # 拆解表的视觉标签（按序号 = weekly 行序）
    wb = openpyxl.load_workbook(XLSX_LAB, read_only=True)
    ws = wb["1_素材总表"]
    it = ws.iter_rows(values_only=True)
    h = list(next(it))
    ix = {x: i for i, x in enumerate(h)}
    lab = {}
    for r in it:
        if r[ix["序号"]] is None:
            continue
        lab[int(r[ix["序号"]]) - 1] = {k: r[ix[k]] for k in h}

    by_file = {r["file"]: r for r in rows}
    items = []
    for i, r in enumerate(rows):
        key = f'{r["product"]}|{r["stem"]}'
        src_key, src = key, "asr"
        if key not in asr and r["file"] in skip:
            rep = skip[r["file"]]
            rep_row = by_file.get(rep)
            if rep_row:
                src_key = f'{rep_row["product"]}|{rep_row["stem"]}'
                src = "dedup"
        v = asr.get(src_key) or {}
        L = lab.get(i, {})
        items.append(dict(
            no=i + 1, product=r["product"], dur=r.get("duration"), file=r["file"],
            fmt=L.get("形态") or "", hook=L.get("钩子") or "", selling=L.get("卖点") or "",
            cta=L.get("CTA") or "", card=L.get("画面文案（原文）") or "",
            breakdown=L.get("中文拆解") or "", conf=L.get("置信") or "",
            cls=(cls.get(src_key) or {}).get("cls") or ("未跑" if not v else v.get("verdict", "未跑")),
            why=(cls.get(src_key) or {}).get("why", ""),
            lang=v.get("lang") or "", text=v.get("text") or "", chars=v.get("chars") or 0,
            zh=zh_key.get(src_key, ""), src=src,
        ))

    wb2 = openpyxl.Workbook()
    ws1 = wb2.active
    ws1.title = "1_口播总表"
    head = ["序号", "产品", "时长s", "形态", "口播判定", "口播语言", "口播字数",
            "口播原文（ASR）", "口播中文（译）", "画面文案（花字）", "钩子", "卖点",
            "CTA", "中文拆解", "置信", "来源"]
    out = []
    for it_ in items:
        out.append([it_["no"], it_["product"], it_["dur"], it_["fmt"], LABEL.get(it_["cls"], it_["cls"]),
                    it_["lang"], it_["chars"], it_["text"], it_["zh"], it_["card"],
                    it_["hook"], it_["selling"], it_["cta"], it_["breakdown"], it_["conf"],
                    "继承" if it_["src"] == "dedup" else ""])
    write_sheet(ws1, head, out, [6, 12, 7, 15, 11, 6, 7, 58, 34, 22, 16, 12, 14, 26, 5, 6],
                wrap_cols=(7, 8, 9, 13))
    for row in ws1.iter_rows(min_row=2, max_row=ws1.max_row, max_col=5):
        lab_v = row[4].value
        row[4].fill = VO_FILL if lab_v == "有口播" else (LYRIC_FILL if lab_v.startswith("歌词") else NONE_FILL)

    groups = defaultdict(list)
    for it_ in items:
        if it_["cls"] == "vo" and norm(it_["text"]):
            groups[norm(it_["text"])].append(it_)
    lib = sorted(groups.values(), key=lambda g: (-len(g), g[0]["product"]))
    ws2 = wb2.create_sheet("2_口播库")
    head2 = ["口播次数", "产品", "口播语言", "口播原文（ASR）", "口播中文（译）", "形态", "画面文案（花字）", "中文拆解"]
    rows2 = []
    for g in lib:
        f = g[0]
        rows2.append([len(g), "、".join(sorted({x["product"] for x in g})), f["lang"], f["text"],
                      f["zh"] or next((x["zh"] for x in g if x["zh"]), ""),
                      f["fmt"], f["card"], f["breakdown"]])
    write_sheet(ws2, head2, rows2, [7, 16, 7, 62, 34, 15, 22, 28], wrap_cols=(3, 6, 7))

    ws3 = wb2.create_sheet("3_无人声清单")
    head3 = ["序号", "产品", "时长s", "形态", "判定", "判定依据", "画面文案（花字）", "中文拆解"]
    rows3 = [[x["no"], x["product"], x["dur"], x["fmt"], LABEL.get(x["cls"], x["cls"]),
              x["why"], x["card"], x["breakdown"]] for x in items if x["cls"] != "vo"]
    write_sheet(ws3, head3, rows3, [6, 12, 7, 15, 11, 14, 40, 30], wrap_cols=(5, 6, 7))

    ws4 = wb2.create_sheet("4_统计")
    tot = len(items)
    vo_n = sum(1 for x in items if x["cls"] == "vo")
    ws4.append([f"1123 期口播体检｜样本 {tot} 条（实转 {sum(1 for x in items if x['src']=='asr')}"
                f" + 继承 {sum(1 for x in items if x['src']=='dedup')}）"
                f"｜有口播 {vo_n}（{vo_n/tot:.1%}）"
                f"｜无人声 {sum(1 for x in items if x['cls']=='none')}"
                f"｜歌词 {sum(1 for x in items if x['cls']=='lyric')}"
                f"｜署名幻觉 {sum(1 for x in items if x['cls']=='credit')}"
                f"｜报错 {sum(1 for x in items if x['cls']=='error')}"])
    ws4.cell(row=1, column=1).font = Font(bold=True, size=11)
    ws4.append([])
    ws4.append(["形态", "条数", "有口播", "有口播率"])
    for c in range(1, 5):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    by = defaultdict(lambda: [0, 0])
    for x in items:
        by[x["fmt"] or "(未标)"][0] += 1
        if x["cls"] == "vo":
            by[x["fmt"] or "(未标)"][1] += 1
    for k, (n, v) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        ws4.append([k, n, v, f"{v/n:.0%}"])
    ws4.append([])
    ws4.append(["语种", "条数", "占样本"])
    for c in range(1, 4):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    for k, n in Counter(x["lang"] for x in items if x["cls"] == "vo").most_common():
        ws4.append([k, n, f"{n/tot:.0%}"])
    ws4.append([])
    ws4.append(["产品", "条数", "有口播", "有口播率"])
    for c in range(1, 5):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    byp = defaultdict(lambda: [0, 0])
    for x in items:
        byp[x["product"]][0] += 1
        if x["cls"] == "vo":
            byp[x["product"]][1] += 1
    for k, (n, v) in sorted(byp.items(), key=lambda kv: -kv[1][1] / max(kv[1][0], 1)):
        ws4.append([k, n, v, f"{v/n:.0%}"])
    for i, w in enumerate([26, 8, 8, 9], 1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    ws5 = wb2.create_sheet("5_口播vs花字")

    def has_card(x):
        return (x["card"] or "").strip() not in ("", "—", "-", "无")

    both = [x for x in items if x["cls"] == "vo" and has_card(x)]
    only_vo = [x for x in items if x["cls"] == "vo" and not has_card(x)]
    only_card = [x for x in items if x["cls"] != "vo" and has_card(x)]
    rows5 = [["两层都有", len(both), "花字是钩子、口播是展开"],
             ["只有口播", len(only_vo), "完全靠人声抓人，无花字钩子"],
             ["只有花字", len(only_card), "无人声，文案靠画面文字承担"],
             ["两层都没有", len(items) - len(both) - len(only_vo) - len(only_card), "纯画面/BGM"]]
    write_sheet(ws5, ["类型", "条数", "说明"], rows5, [14, 8, 46], wrap_cols=(2,))
    ws5.append([])
    ws5.append(["复投口播（同一条口播出现在多条素材）", "条数", "产品"])
    for c in range(1, 4):
        ws5.cell(row=ws5.max_row, column=c).fill = HEAD_FILL
        ws5.cell(row=ws5.max_row, column=c).font = HEAD_FONT
    for g in lib:
        if len(g) > 1:
            ws5.append([g[0]["text"][:90], len(g), "、".join(sorted({x["product"] for x in g}))])
    for row in ws5.iter_rows(min_row=2, max_row=ws5.max_row, max_col=3):
        for c in row:
            c.font = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=c.column == 1)

    wb2.save(XLSX_OUT)
    miss = sum(1 for x in items if x["cls"] == "vo" and not x["zh"])
    print(f"saved {XLSX_OUT}")
    print(f"总表 {tot} | 有口播 {vo_n} | 口播库 {len(lib)} 组（复投 {sum(1 for g in lib if len(g)>1)} 组）"
          f" | 非口播 {len(rows3)} | 缺译文 {miss}")


if __name__ == "__main__":
    main()
