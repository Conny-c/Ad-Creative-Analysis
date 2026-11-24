---
name: competitor-creative-pipeline
description: >
  MUST USE when the user runs a **weekly competitor ad-material pipeline** on a local
  素材库（不是单条视频的临时拆解）：每周更新清单/下载、素材去重、周更技术分析、
  视觉打标、口播转录、增量台账、出拆解表或口播表。典型说法：跑这周的竞品、
  跑一下周更、这批新增多少条、打标出表、口播转录、声纹查重、只跑新增、
  台账/累积/下周复用、分析 8-竞品素材分析.bat 为什么闪退。
  Covers: 目录约定、md5+画面+音频三层查重、有无人声体检（幻觉白名单、medium 复查）、
  唯一段去重再翻译、四页签拆解表与五页缺口播表、三张累积台账与继承机制、常见踩坑。
  适用 20+ 竞品、上千条素材、多语种混批的周更产线。
  NOT for: 单条/几条视频的临时拆解 → 用 `competitor-video-teardown`；
  有买量表要做 install/CPI/次留归因 → 用 `tiktok-creative-analysis`。
triggers:
  - 周更: 跑这周/周更/本期更新/新增多少条/增量
  - 产线: 下载清单/素材去重/打标出表/口播转录/台账/只跑新增
  - 排障: bat 闪退/跑不动/路径找不到/卡住/太慢
  - 交付: 拆解表/口播表/文案库/产品画像/小结
metadata:
  domain: competitor-creative
  pipeline: weekly
  scripts_root: analysis/tools
  scale: 20-40 competitors / 1000-2500 creatives per issue
---

# 竞品素材周更产线

一条已经跑通的周更流水线：**抓取 → 去重 → 周更体检 → 打标 → 口播转录 → 台账 → 出表**。
目标不是"描述素材"，而是产出能直接改脚本的结论。

> 单条或少量视频的临时拆解、没有既定目录结构 → 走 `competitor-video-teardown`。

---

## 0. 先确认三件事

| 问题 | 不确认会怎样 |
|---|---|
| 本期口径：**TOP5** 还是 **ALL**？ | ALL 会把全量写进台账，之后再跑 TOP5 会显示"新增 0" |
| 素材目录在哪（`<根>\<YYYY-MM-DD>\<产品>\*.mp4`）？ | 期号、印相路径、sheet 列全靠它 |
| 是新开一期，还是续跑昨天没跑完的？ | 续跑走 `asr.json` 断点，重跑会白烧算力 |

---

## 1. 目录与命名（照这个放，脚本才认）

```
<根>\
├─ <YYYY-MM-DD>\<产品>\*.mp4        素材，文件名 <产品>_<来源>_<地区>_<8位hash>.mp4
├─ analysis\
│  ├─ tools\                        所有脚本
│  ├─ models\                       faster-whisper（不要放 HF 缓存，那份在工作区外）
│  ├─ assets\sheets_<期号>\*.jpg     6 帧印相，1200×840
│  └─ data_<期号>\                  probe/rhythm/asr/audio/wl/labels/zh
└─ out\                    三张台账 + 每周交付物
```

主键共三个，别混：
`md5`（跨周唯一）· `product|stem`（单期内唯一）· `序号`（= weekly CSV 行序，拆解表用它对齐）。

---

## 2. 每周动作（按顺序，别跳）

### 2.1 采集

双击 `1-更新下载清单` → `2-查看可选` → `3-挑选下载` / `4-全部下载`；或一把梭 `0-每周一键`。
下载器按 `封面+时长+中间帧` 自去重，重复的删掉并记到 `list\<日期>.csv`。

### 2.2 素材级去重（文件层）

`5-去重体检`（跨格式同内容）· `7-按封面去重`（报告）· `9-空间回收`（跨周硬链接）。
这一层只管"同一支片子被下两次"，**挡不住"换编码重传"**——那要靠 2.6 的音频指纹。

### 2.3 周更体检（`8-竞品素材分析.bat`）

输期号（回车=今天）+ 范围（回车=TOP5 / `ALL` / 产品名）。内部 5 步：

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 探针 | `probe.py` | 时长/画幅/码率/切点/md5 → `data_<期号>\probe.csv` |
| 印相 | `sheets.py` | 每条 6 帧拼图 → `assets\sheets_<期号>\` |
| 节奏 | `rhythm.py` | 帧差密度 / RMS / 静音比 / 语音调制 |
| AI 信号 | `ai_detect.py` | C2PA 凭证 + 平台 AIGC 标记 |
| AI 候选 | `ai_candidates.py` | 按风险排序的复核清单 |

`weekly.py` 再与 `master_ledger.csv` 做 md5 差集 → `out\weekly_<期号>_新增.csv`。

**完成标志**：`本期 N 条，新增 M 条，历史 K 条` + `请按任意键继续`。
`sheets.py` 全程无输出（只在结尾打印 `built/skipped/failed`），想估进度就数 jpg 数量。

### 2.4 视觉打标

```bash
python scripts/make_worklist.py --csv out/weekly_<期号>_新增.csv \
    --out data_<期号>/wl_<期号>.json --batches 24
```

切批 → 每条给一个子任务：`read_image` 看印相 → 按 `guides/label_guide_v2.md` 的**固定枚举**打标 →
写 `data_<期号>/labels/labels_bNN.json`。

- 并发上限按运行环境定（DSH 里同时最多 8 个子任务，超了会报 `subagent limit reached`）
- 打完必须跑 `validate_labels.py`：覆盖数、`idx/file` 对齐、枚举越界、空值，四项全过才出表

```bash
python scripts/build_labels_xlsx.py --wl ... --labels ... --csv ... --out ...
```

### 2.5 口播转录

**先查重再转**，这一步省的时间最多：

```bash
# 1) 音频指纹聚类（顺带抽好 16k wav，转写直接复用）
python scripts/audio_dup.py --csv out/weekly_<期号>_新增.csv \
    --audio data_<期号>/audio --out data_<期号>/audio_dup.json --extract --workers 16

# 2) 画面+音频合并，出代表条清单
python scripts/make_dedupe_list.py --csv out/weekly_<期号>_新增.csv \
    --audio-dup data_<期号>/audio_dup.json \
    --out-csv out/weekly_<期号>_新增_去重.csv --out-map data_<期号>/dedupe_map.json

# 3) 只转代表条；--ledger 会自动继承台账里已有的（md5 命中 / 音频指纹命中）
python scripts/asr_batch.py --csv out/weekly_<期号>_新增_去重.csv \
    --model <small 模型目录> --out data_<期号>/asr.json \
    --audio data_<期号>/audio --threads 16

# 4) 二次判定
python scripts/classify_vo.py --asr data_<期号>/asr.json --out data_<期号>/vo_class.json

# 5) 三层去重 → 唯一段
python scripts/build_vo_unique.py
```

判错的用 `data_<期号>/vo_override.json` 按 key 改判（日文乱码歌词、`Beadaholique` 这类幻觉串、非本市场语种乱码）。
**只译唯一段**，译文按 `zh/zh_bNN.json` 回填 → `vo_zh.json` → 出表（`build_vo_1123.py` 带继承回填）。

### 2.6 沉淀（下周省钱的关键）

```bash
python scripts/build_label_ledger.py
python scripts/build_voice_ledger.py --all
```

三张台账：`master_ledger.csv`（md5 技术）· `label_ledger.csv`（视觉标签）· `voice_ledger.csv`（口播+音频指纹）。

---

## 3. 查重口径（四层，从硬到软）

| 层 | 判据 | 强度 | 能挡什么 |
|---|---|---|---|
| 文件 | md5 相同 | 最硬 | 重复下载 |
| 画面 | 6 帧印相 aHash+dHash 汉明 ≤18/256 | 强 | 换编码/换分辨率 |
| 声音 | 音频 shingle Jaccard ≥0.7 + 时长差 <8% | 强 | **同一条旁白换画面** |
| 文案 | 花字+时长相同+文本相似 ≥0.85 | 中 | 同钩子换演员 |

**关键经验**：花字一样 ≠ 口播一样。花字是钩子（3–5 字），口播是展开（30–90 字）；
实测"花字+时长相同但画面不同"的组里，只有 **43%** 的口播文本一致。所以第四层只能事后合并，不能预筛。

音频指纹必须加两道约束，否则会把"同一首 BGM"判成同一段声音：
**时长差 <8%** + **至少 9 秒**（shingle 少于 6 个的片段不参与，静音片段天然不合格）。

---

## 4. 有无人声口径

每条素材必须落进四类之一，不允许留空：

| 判定 | 处理 |
|---|---|
| `vo` 真口播 | 进表，原文 + 译文 |
| `none` 无人声 | 单列清单，与花字对照 |
| `lyric` 歌词 | 不进文案库 |
| `credit` 片尾署名/幻觉 | 剔除 |

- 幻觉白名单必备：`thanks for watching` / `music` / `구독과 좋아요` / `Altyazı M.K.` / `beadaholique` …
- **VAD 复查只在 5–19 字之间做**。0–4 字基本都是纯音乐，复查是白跑一整遍（实测把吞吐从 1.1x 拉回 8.5x）
- `none` 必须复查过一次（medium + 关 VAD），否则没法回答"是没人声还是漏转"

---

## 5. 时间预算（2094 条全量实测）

| 环节 | 耗时 |
|---|---|
| 周更 5 步 | 15 min |
| 打标（1530 条 / 24 批） | 40 min |
| 音频查重 + 抽音轨 + 指纹 | 6 min |
| 转写（1316 条 / 485 min 音频） | 85 min |
| 唯一段翻译（932 段） | 30 min |
| 出表 + 台账 | 5 min |

有台账后的下一期：转写量降到 **300–600 条**，整期压到 1 小时内。

---

## 6. 坑（每条都真踩过）

1. **`.bat` 必须 CRLF**。LF 换行会让 cmd 解析错位，双击一闪就关（报 `'ause' 不是内部命令` 就是这病）。
2. **脚本不许硬编码绝对路径**。历史遗留的 `D:\...\video-analysis` 换个机器就是 `PermissionError`；统一走环境变量或 `Path(__file__).parent.parent`。
3. **模型别放 HF 缓存**。`~/.cache/huggingface` 在工作区外、沙箱只读，会卡在"补下载"十分钟没动静。下到工作区。
4. **沙箱里跑不了抽帧脚本**。python 在受限环境 `chmod` 被拒，`TemporaryDirectory` 清理抛 `PermissionError`；要么提权，要么让用户直接双击 bat。
5. **xlsx 别塞原图**。1530 张原图 ≈170MB；360px/q55 缩略图 ≈30MB；再小就看不清 6 帧里的字。
6. **`ALL` 会污染台账**。跑 ALL 之前先备份 `weekly_<期号>_新增.csv`，否则 TOP5 口径回不来。
7. **md5 挡不住重传**。2094 条里 md5 已去 564 条，仍有 214 条是换壳同内容。
8. **印相判不了口播**。6 帧只能看画面，有没有人声必须 ASR，别按形态猜。
9. **纯静音素材不参与指纹继承**（只有 1 个 shingle），只走 md5——这是有意的，避免"都安静"被判成同一条。
10. **同一条素材被切成多行**时先查 md5 是否重复，再查是不是"同画面不同时长"。

---

## 7. 交付检查

- [ ] 每条素材都有判定，`none` 是复查过的，不是漏转
- [ ] 幻觉白名单命中项没有混进文案列
- [ ] 打标枚举 0 越界，`序号` 与素材清单 100% 对齐
- [ ] 低置信（0.5）单独标色并说明集中在哪
- [ ] 拆解表/口播表里"继承"的条目有来源列
- [ ] 结论至少有一条是「同文案换画面」或「同素材换壳」的对照
- [ ] 小结里写明本期口径（TOP5 / ALL / 指定产品），以及与上期是否可比

---

## 8. 脚本索引（`analysis/tools`）

| 阶段 | 脚本 |
|---|---|
| 周更 | `weekly.py` `probe.py` `sheets.py` `rhythm.py` `ai_detect.py` `ai_candidates.py` |
| 打标 | `make_worklist.py` `validate_labels.py` `build_labels_xlsx.py` `build_label_ledger.py` |
| 口播 | `asr_batch.py` `fetch_model.py` `classify_vo.py` `make_overrides.py` `build_vo_unique.py` `build_vo_1123.py` `build_voice_ledger.py` |
| 查重 | `dupcheck.py` `audio_dup.py` `make_dedupe_list.py` `combine_dedupe.py` |
| 诊断 | `estimate_vo.py` `spot_check_vo.py` `check_delivery.py` `card_dur_split.py` |

## 9. 参考

- `references/摘要_1页.md` —— 给业务方的一页说明（可直接外发）
- `references/SOP_周更执行.md` —— 给接手同事的分步清单（含验收与异常处理）
- `references/案例_1123_全量32产品.md` —— 一次全量实战的数字、结论与返工点
- `references/流程_对外版.md` —— 对外版完整流程（方法/口径/边界）
