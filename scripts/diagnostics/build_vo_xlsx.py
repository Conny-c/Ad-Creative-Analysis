# -*- coding: utf-8 -*-
"""把 asr.json + vo_class.json 落成 11-09 那版口径的口播工作簿（5 页签）。

口径对齐 2026-11-09 拆解表：
  1_口播总表   每条素材一行：口播判定 / 口播语言 / 原文(ASR) / 中文译 / 画面文案(花字)
  2_口播库     真口播原文去重 + 出现次数（复投口播 = 同一条口播换画面）
  3_无人声清单 非真口播的素材（含歌词/署名幻觉），带形态和花字
  4_统计       形态×有口播率 / 语种分布 / 产品×有口播率
  5_口播vs花字 两层都有 / 只有口播 / 只有花字
"""
import argparse, csv, json, math, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

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


def write_sheet(ws, head, rows, widths, wrap_cols=(), freeze="A2"):
    ws.append(head)
    for c in range(1, len(head) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for r in rows:
        ws.append(list(r))
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = freeze
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(head)):
        lines = 1
        for c in row:
            wrap = c.column - 1 in wrap_cols
            c.alignment = Alignment(vertical="top", wrap_text=wrap)
            c.font = Font(size=9)
            if wrap:
                lines = max(lines, math.ceil(wlen(c.value) / max(widths[c.column - 1] - 1, 4)))
        ws.row_dimensions[row[0].row].height = min(13.5 * max(lines, 1) + 3, 170)


def load_labels():
    """11-16 拆解表：序号 -> 打标字段（形态/钩子/卖点/CTA/花字/拆解/置信）"""
    p = r"E:\video-download\analysis\out\2026-11-16_竞品素材拆解表.xlsx"
    wb = openpyxl.load_workbook(p, read_only=True)
    ws = wb["1_素材总表"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    ix = {h: i for i, h in enumerate(hdr)}
    out = {}
    for r in it:
        if r[ix["序号"]] is None:
            continue
        out[int(r[ix["序号"]])] = dict(
            product=r[ix["产品"]], dur=r[ix["时长s"]], fmt=r[ix["形态"]],
            person=r[ix["人物"]], scene=r[ix["场景"]], hook=r[ix["钩子"]],
            selling=r[ix["卖点"]], cta=r[ix["CTA"]], card=r[ix["画面文案（原文）"]],
            breakdown=r[ix["中文拆解"]], conf=r[ix["置信"]],
        )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=r"E:\video-download\analysis\out\weekly_20261116_新增.csv")
    ap.add_argument("--asr", default=r"E:\video-download\analysis\data_20261116\asr.json")
    ap.add_argument("--class", dest="clsf", default=r"E:\video-download\analysis\data_20261116\vo_class.json")
    ap.add_argument("--zh", default=r"E:\video-download\analysis\data_20261116\vo_zh.json")
    ap.add_argument("--out", default=r"E:\video-download\analysis\out\2026-11-16_口播转录表.xlsx")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    asr = json.loads(Path(a.asr).read_text(encoding="utf-8"))
    cls = json.loads(Path(a.clsf).read_text(encoding="utf-8")) if Path(a.clsf).exists() else {}
    zh = json.loads(Path(a.zh).read_text(encoding="utf-8")) if Path(a.zh).exists() else {}
    labels = load_labels()

    items = []
    for i, r in enumerate(rows, 1):
        key = f'{r["product"]}|{r["stem"]}'
        v = asr.get(key) or {}
        lab = labels.get(i, {})
        assert str(lab.get("product")) == r["product"], f"行序错位 {i}"
        c = (cls.get(key) or {}).get("cls") or (v.get("verdict") if v else "未跑")
        txt = v.get("text") or ""
        items.append(dict(
            key=key, no=i, product=r["product"], stem=r["stem"], dur=r.get("duration"),
            fmt=lab.get("fmt") or "", hook=lab.get("hook") or "",
            selling=lab.get("selling") or "", cta=lab.get("cta") or "",
            card=lab.get("card") or "", breakdown=lab.get("breakdown") or "",
            conf=lab.get("conf") or "", person=lab.get("person") or "",
            scene=lab.get("scene") or "",
            cls=c, why=(cls.get(key) or {}).get("why", ""),
            lang=v.get("lang") or "", text=txt, chars=v.get("chars") or 0,
            zh=zh.get(key, "") or zh.get(norm(txt), ""),
        ))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "1_口播总表"
    head = ["序号", "产品", "时长s", "形态", "口播判定", "口播语言", "口播字数",
            "口播原文（ASR）", "口播中文（译）", "画面文案（花字）", "钩子", "卖点",
            "CTA", "中文拆解", "置信", "判定依据"]
    rows_out = []
    for it in items:
        rows_out.append([it["no"], it["product"], it["dur"], it["fmt"],
                         LABEL.get(it["cls"], it["cls"]), it["lang"], it["chars"], it["text"],
                         it["zh"], it["card"], it["hook"], it["selling"], it["cta"],
                         it["breakdown"], it["conf"], it["why"]])
    write_sheet(ws, head, rows_out, [6, 11, 7, 15, 11, 6, 7, 58, 34, 22, 16, 12, 14, 26, 5, 14],
                wrap_cols=(7, 8, 9, 13))
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=5):
        lab = row[4].value
        row[4].fill = VO_FILL if lab == "有口播" else (LYRIC_FILL if lab.startswith("歌词") else NONE_FILL)

    # 2_口播库
    groups = defaultdict(list)
    for it in items:
        if it["cls"] == "vo" and norm(it["text"]):
            groups[norm(it["text"])].append(it)
    lib = sorted(groups.values(), key=lambda g: (-len(g), g[0]["product"]))
    ws2 = wb.create_sheet("2_口播库")
    head2 = ["口播次数", "产品", "口播语言", "口播原文（ASR）", "口播中文（译）",
             "形态", "画面文案（花字）", "中文拆解"]
    rows2 = []
    for g in lib:
        f = g[0]
        rows2.append([len(g), "、".join(sorted({x["product"] for x in g})), f["lang"], f["text"],
                      f["zh"] or next((x["zh"] for x in g if x["zh"]), ""),
                      f["fmt"], f["card"], f["breakdown"]])
    write_sheet(ws2, head2, rows2, [7, 14, 7, 62, 34, 15, 22, 28], wrap_cols=(3, 6, 7))

    # 3_无人声清单
    ws3 = wb.create_sheet("3_无人声清单")
    head3 = ["序号", "产品", "时长s", "形态", "判定", "判定依据", "画面文案（花字）", "中文拆解"]
    rows3 = [[it["no"], it["product"], it["dur"], it["fmt"], LABEL.get(it["cls"], it["cls"]),
              it["why"], it["card"], it["breakdown"]] for it in items if it["cls"] != "vo"]
    write_sheet(ws3, head3, rows3, [6, 12, 7, 15, 11, 14, 40, 30], wrap_cols=(5, 6, 7))

    # 4_统计
    ws4 = wb.create_sheet("4_统计")
    tot = len(items)
    vo_n = sum(1 for it in items if it["cls"] == "vo")
    ws4.append([f"1116 期口播体检｜样本 {tot} 条｜有口播 {vo_n}（{vo_n/tot:.1%}）"
                f"｜无人声 {sum(1 for it in items if it['cls']=='none')}"
                f"｜歌词 {sum(1 for it in items if it['cls']=='lyric')}"
                f"｜署名幻觉 {sum(1 for it in items if it['cls']=='credit')}"
                f"｜报错 {sum(1 for it in items if it['cls']=='error')}"])
    ws4.cell(row=1, column=1).font = Font(bold=True, size=11)
    ws4.append([])

    ws4.append(["形态", "条数", "有口播", "有口播率"])
    for c in range(1, 5):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    by = defaultdict(lambda: [0, 0])
    for it in items:
        by[it["fmt"] or "(未标)"][0] += 1
        if it["cls"] == "vo":
            by[it["fmt"] or "(未标)"][1] += 1
    for k, (n, v) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        ws4.append([k, n, v, f"{v/n:.0%}"])
    ws4.append([])
    ws4.append(["语种", "条数", "占样本"])
    for c in range(1, 4):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    for k, n in Counter(it["lang"] for it in items if it["cls"] == "vo").most_common():
        ws4.append([k, n, f"{n/tot:.0%}"])
    ws4.append([])
    ws4.append(["产品", "条数", "有口播", "有口播率"])
    for c in range(1, 5):
        ws4.cell(row=ws4.max_row, column=c).fill = HEAD_FILL
        ws4.cell(row=ws4.max_row, column=c).font = HEAD_FONT
    byp = defaultdict(lambda: [0, 0])
    for it in items:
        byp[it["product"]][0] += 1
        if it["cls"] == "vo":
            byp[it["product"]][1] += 1
    for k, (n, v) in sorted(byp.items(), key=lambda kv: -kv[1][1] / max(kv[1][0], 1)):
        ws4.append([k, n, v, f"{v/n:.0%}"])
    for i, w in enumerate([26, 8, 8, 9], 1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    # 5_口播vs花字
    ws5 = wb.create_sheet("5_口播vs花字")
    head5 = ["类型", "条数", "说明"]

    def has_card(it):
        return (it["card"] or "").strip() not in ("", "—", "-", "无", "没", "未标注", "无花字")

    both = [it for it in items if it["cls"] == "vo" and has_card(it)]
    only_vo = [it for it in items if it["cls"] == "vo" and not has_card(it)]
    only_card = [it for it in items if it["cls"] != "vo" and has_card(it)]
    rows5 = [
        ["两层都有", len(both), "花字是钩子、口播是展开，两条都留"],
        ["只有口播", len(only_vo), "完全靠人声抓人，无花字钩子"],
        ["只有花字", len(only_card), "无人声，文案全靠画面文字承担"],
        ["两层都没有", len(items) - len(both) - len(only_vo) - len(only_card), "纯画面/BGM，文案层缺失"],
    ]
    write_sheet(ws5, head5, rows5, [14, 8, 46], wrap_cols=(2,))
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

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    wb.save(a.out)

    # 旁路：按「序号」对齐的 CSV，方便 VLOOKUP 回 2026-11-16_竞品素材拆解表
    import csv as _csv
    csv_path = Path(a.out).with_name(Path(a.out).stem.replace("口播转录表", "口播合并") + ".csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(["序号", "产品", "口播判定", "口播语言", "口播字数", "口播原文(ASR)", "口播中文(译)", "判定依据"])
        for it in items:
            w.writerow([it["no"], it["product"], LABEL.get(it["cls"], it["cls"]), it["lang"],
                        it["chars"], it["text"], it["zh"], it["why"]])
    print("saved", csv_path)
    print("saved", a.out)
    print(f"总表 {tot} | 有口播 {vo_n} | 口播库 {len(lib)} 组 "
          f"(复投 {sum(1 for g in lib if len(g) > 1)} 组) | 非口播 {len(rows3)}")


if __name__ == "__main__":
    main()
