# 周更执行 SOP（接手用）

> 目标：一个人照这份清单，能把一期从"下载"跑到"两张表 + 台账"。
> 每一步都给：入口 / 命令 / 预期输出 / 验收。**验收不过不要往下走。**

---

## 0. 开工前检查（5 分钟）

- [ ] `ffmpeg` / `ffprobe` 在 PATH，或 `C:\ffmpeg\bin\`
- [ ] python 可用，`faster-whisper` + `ctranslate2` 已装
- [ ] small 模型目录存在（口播用）；`models\medium` 存在（复查用）
- [ ] 素材目录 `<根>\<YYYY-MM-DD>\<产品>\*.mp4` 已就位
- [ ] `out\` 下三张台账存在（`master_ledger.csv` / `label_ledger.csv` / `voice_ledger.csv`）

**口径先定**：本期是 **TOP5** 还是 **ALL**？
选 ALL 前先把上一期的 `weekly_<期号>_新增.csv` 备份一份——ALL 会把全量写进台账，之后 TOP5 会显示"新增 0"。

---

## 1. 下载（约 20–60 分钟，看量）

```
双击 1-更新下载清单.bat      → 重建 list\
双击 2-查看有哪些可选.bat    → 只列不下载，确认这次抓到了谁
双击 3-挑选下载(交互).bat    → 挑竞品
双击 4-全部下载.bat          → 全下
（或 0-每周一键.bat 一次跑完上面 + 去重）
```

验收：目标目录下 mp4 数量与清单一致；`list\<日期>.csv` 有记录。

---

## 2. 素材级去重

```
5-去重体检.bat          → 报告跨格式同内容
7-按封面去重(仅报告).bat → 报告封面+时长+中间帧重复
9-空间回收(仅报告).bat   → 报告跨周硬链接可省空间
```

三个都是**只报告**。要真删/真链，按提示加 `-Apply` 手动跑。
验收：报告里的重复项已确认（同一条片子不该进两次）。

---

## 3. 周更体检（15 分钟）

```
双击 8-竞品素材分析.bat
  期号：20261123（回车=今天）
  范围：回车=TOP5 / ALL / 产品名
```

跑 5 步：探针 → 印相 → 节奏 → AI 信号 → AI 候选，然后与 `master_ledger.csv` 差集。

**预期输出**：

```
--- probe.py ---   files: 2094
--- sheets.py ---  built: 2094 skipped: 0 failed: 0
--- rhythm.py ---  rhythm ok: 2094 audio ok: 2094
--- ai_detect.py -- 凭证确认 11 条
本期 2094 条，新增 1530 条，历史 2480 条
完成：... out\weekly_20261123_新增.csv
请按任意键继续. . .
```

验收：
- [ ] 新增条数 > 0
- [ ] `assets\sheets_<期号>\` 的 jpg 数 ≈ 素材数
- [ ] 运行中若长时间无输出 → 数 jpg 判断是否在动（`sheets.py` 只在结束时打印）

---

## 4. 视觉打标（40 分钟）

```bash
python scripts\make_worklist.py --csv out\weekly_<期号>_新增.csv \
    --out data_<期号>\wl_<期号>.json --batches 24
```

按批给子任务：`read_image` 看印相 → 按 `guides\label_guide_v2.md` 的固定枚举打标 →
写 `data_<期号>\labels\labels_bNN.json`。

- 并发上限按环境来（DSH 同时最多 8 个），超了会 `subagent limit reached`
- 枚举值必须原样复制，不许自创/翻译
- 每批回一行 `done <路径> <条数>`

```bash
python scripts\validate_labels.py       # 四项必须全过
python scripts\build_labels_xlsx.py --wl ... --labels ... --csv ... --out ...
```

验收：
- [ ] 缺 0 / 多 0，`idx`+`file` 与 worklist 100% 对齐
- [ ] 枚举越界 0
- [ ] `summary` 无缺失、无超 40 字
- [ ] 拆解表 4 个页签都在，印相没压行

---

## 5. 口播转录（2 小时左右）

```bash
# 1) 音频指纹 + 抽音轨（顺带把 wav 缓存备好）
python scripts\audio_dup.py --csv out\weekly_<期号>_新增.csv \
    --audio data_<期号>\audio --out data_<期号>\audio_dup.json --extract --workers 16

# 2) 画面+音频合并 -> 代表条清单
python scripts\make_dedupe_list.py --csv out\weekly_<期号>_新增.csv \
    --audio-dup data_<期号>\audio_dup.json \
    --out-csv out\weekly_<期号>_新增_去重.csv --out-map data_<期号>\dedupe_map.json

# 3) 只转代表条（台账已有的会自动继承）
python scripts\asr_batch.py --csv out\weekly_<期号>_新增_去重.csv \
    --model "<small 模型目录>" --out data_<期号>\asr.json \
    --audio data_<期号>\audio --threads 16

# 4) 二次判定
python scripts\classify_vo.py --asr data_<期号>\asr.json --out data_<期号>\vo_class.json

# 5) 三层去重 -> 唯一段
python scripts\build_vo_unique.py
```

**建议另开一个窗口跑第 3 步**，它是最长的一步（1316 条约 85 分钟），可随时中断，
`asr.json` 每条写完就存，断了重跑只会补剩下的。

验收：
- [ ] `asr.json` 条数 = 去重后代表条数
- [ ] 判定分布合理（真口播 / 无人声 / 歌词 / 署名），无大量"报错"
- [ ] 唯一段数量与预期接近（一般比真口播少 10–40%）

---

## 6. 翻译（30 分钟）

只译**唯一段**：`build_vo_unique.py` 产出的 `vo_unique.json` 切批 → 译 → `zh\zh_bNN.json`。

翻译规范：
- 口语化中文，App 名保留原文（GRAVITY/Zili/Sugo/Litmatch/Tango…）
- ASR 错字按语义还原，不逐字硬译
- 实在听不清写 `（无法辨认）`
- 一条不漏，key 必须等于 `rid`

验收：`vo_zh.json` 覆盖率 100%，抽查 5 条语义通顺。

---

## 7. 出表 + 台账

```bash
python scripts\build_vo_1123.py      # 口播表（含继承回填）
python scripts\build_label_ledger.py # 打标台账
python scripts\build_voice_ledger.py --all   # 语音台账（含音频指纹）
```

验收：
- [ ] 口播表 5 个页签齐全，缺译文 0，"继承"列标出被合并的条目
- [ ] 三张台账行数 = 累计素材数（不重复）
- [ ] 小结 md 写明本期口径与与上期的可比性

---

## 8. 异常处理

| 现象 | 原因 | 处理 |
|---|---|---|
| bat 双击一闪就关 | 文件是 LF 换行 | 转 CRLF |
| `PermissionError: ...video-analysis` | 脚本里硬编码了旧路径 | 改用 `SUGO_WORK` / 脚本自身位置 |
| 卡在"加载模型"十分钟 | 模型在只读缓存里补下载 | 用 `fetch_model.py` 下到工作区 |
| 抽帧阶段 PermissionError | 受限环境不能 chmod/删临时目录 | 提权，或用户直接双击 bat |
| 转写只有 1.1x 实时 | 纯音乐素材也在跑 VAD 复查 | 复查条件收窄到 5–19 字 |
| ALL 跑完后再跑 TOP5 显示新增 0 | 台账已被全量填满 | 用备份的 weekly CSV 还原口径 |
| xlsx 打不开/极慢 | 塞了原图 | 印相缩略图压到 360px/q55 |

---

## 9. 交接时要说清的三件事

1. **本期口径**（TOP5 / ALL / 指定产品），以及和上期是否可比
2. **台账状态**（三张表各自覆盖到哪一期、多少行）
3. **没做完的地方**（哪一步中断、断点文件在哪、下一步从哪条命令接）
