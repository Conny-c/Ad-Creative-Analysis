# 竞品素材分析产线（可复用包）

竞品短视频买量素材的**周更流水线**：抓取 → 去重 → 技术体检 → 视觉打标 → 口播转录 → 台账 → 出表。

产出两样东西：

- **《竞品素材拆解表》**：每条素材一行，形态 / 人物 / 场景 / 钩子 / 卖点 / CTA / 露出时点 / 文案 / 拆解 + 6 帧预览图
- **《口播转录表》**：每条素材的口播原文 + 中文译文 + 是否有口播的判定

> 只看素材本身在讲什么，**不做投放效果**（install / CPI / 次留）归因——那需要买量表。

---

## 包结构

```
competitor-creative-pipeline\
├─ SKILL.md                 技能定义：口径、六步流程、查重四层、坑、检查清单
├─ README.md
├─ scripts\                 产线核心脚本（21 个）
│  └─ diagnostics\          一次性分析/验证脚本（15 个，路径写死，用前改）
├─ guides\                  打标规范（固定枚举，别自创）
│  ├─ label_guide_v2.md     视觉打标：形态/人物/语言/钩子/露出/CTA/规格/卖点
│  ├─ label_guide_ai.md     AI 素材判定（只认内容凭证）
│  └─ label_guide.md        早期版，参考
├─ collection\              采集层：7 个 ps1 + 对应 bat 入口
├─ references\              摘要 / SOP / 案例 / 对外流程
├─ examples\                一期全量的交付物样本（带印相的表 + 全量 CSV + 小结）
├─ docs\                    对外版流程（md + docx）
└─ out\                     台账与交付物落地目录（空）
```

## 先看哪两个

- **给业务方**：`references/摘要_1页.md`
- **给接手的人**：`references/SOP_周更执行.md`（分步 + 验收 + 异常处理）

## 跑起来需要什么

| 依赖 | 用途 |
|---|---|
| python 3.10+ | 全部脚本 |
| `ffmpeg` / `ffprobe` | 抽帧、抽音轨、探针 |
| `faster-whisper` + `ctranslate2` | 口播转录（CPU int8 即可） |
| `openpyxl` `Pillow` `numpy` `pandas` | 出表、拼图、分析 |
| whisper 模型 | `scripts/fetch_model.py` 下到本地 `models\`（**别放 HF 缓存**） |

```
python scripts/fetch_model.py Systran/faster-whisper-small models/small
python scripts/fetch_model.py Systran/faster-whisper-medium models/medium
```

## 一周的流程

```
# 1) 采集（Windows，双击或用 PowerShell）
collection\1-更新下载清单.bat      # 抓清单
collection\4-全部下载.bat          # 或 3-挑选下载
collection\5-去重体检.bat          # 素材级去重（报告）

# 2) 技术体检：探针 + 6 帧印相 + 节奏 + AI 信号 + md5 差集
python scripts/weekly.py --date 20261123 --root "E:\video-download" --work "analysis" --top5

# 3) 视觉打标：切批 -> 看图打标（label_guide_v2）-> 自检 -> 出表
python scripts/make_worklist.py --csv analysis/out/weekly_20261123_新增.csv \
    --out analysis/data_20261123/wl.json --batches 24
python scripts/validate_labels.py
python scripts/build_labels_xlsx.py --wl ... --labels ... --csv ... --out ...

# 4) 口播：先查重，再只转代表条
python scripts/audio_dup.py --csv ... --audio analysis/data_20261123/audio \
    --out analysis/data_20261123/audio_dup.json --extract --workers 16
python scripts/make_dedupe_list.py --csv ... --audio-dup ... --out-csv ... --out-map ...
python scripts/asr_batch.py --csv ... --model models/small --out analysis/data_20261123/asr.json \
    --audio analysis/data_20261123/audio --threads 16
python scripts/classify_vo.py --asr ... --out analysis/data_20261123/vo_class.json
python scripts/build_vo_unique.py

# 5) 台账（下周只跑新增）
python scripts/build_label_ledger.py
python scripts/build_voice_ledger.py --all
```

## 路径说明（重要）

脚本的**默认路径**指向作者本机（`E:\video-download\analysis\...`）。换机器或其他目录时：

- 优先用参数覆盖：`weekly.py --root/--work`、`asr_batch.py --csv/--model/--out/--audio`
- 或改文件顶部的常量（`ROOT` / `OUT` / `TOOLS` 之类）
- `scripts/diagnostics/` 下的脚本是**按某一期写死**的，用前先改路径

## 这套东西的核心结论

**抓取量 ≠ 工作量。** 最近一期全量的漏斗：

```
2094 抓取 → 1530 账面新增 → 1316 真正要转写 → 967 有真口播 → 932 唯一口播段
```

中间约 40% 是重复（换编码、换画面、重复上传），靠 md5 + 画面指纹 + 音频指纹三层剥掉。
台账建好之后，同类规模的一期只需转 300–600 条。

## 已知边界

- 只看公开投放素材；"地区"是数据源标注，不等于真实投放配置
- 口播来自 ASR，人名/品牌名会有音转字误差；译文为逐段翻译，长句有压缩
- AI 生成只认内容凭证，视觉判断只作"疑似"
- 结构分布受样本构成影响，报告里必须注明本期口径
