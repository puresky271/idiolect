---
name: idiolect-distill
description: "Turn a corpus into the derived statistics that idiolect ships and consumes: per-character style profiles, per-scene length targets, tic profiles, per-scene tics, topic vocabularies and the character x scene baseline. Use this skill whenever the user wants to recompute data/ from their own corpus, asks which script produces which file under data/, needs to regenerate idiolect/scene_length_targets.py, hits a scene-coverage or style-profile mismatch after changing the corpus, or asks why two runs of the same script produced different files. Covers the exact generation commands, the publish form (--no-exemplars), the determinism requirement, and how to verify the shipped data can be rebuilt."
---

# idiolect-distill：从语料产出派生统计

这一节把语料变成**五类特征的统计底表**。产物分两处：

- `data/`：随仓库发布的聚合量（无原作文本）；
- `idiolect/scene_length_targets.py`：包内代码，130 个「角色 × 场景」长度目标。

前置：语料已就绪（[`idiolect-corpus`](../idiolect-corpus/SKILL.md)）。权威细节见 [`docs/03-features.md`](../../../docs/03-features.md) 与 [`docs/02-corpus.md`](../../../docs/02-corpus.md) 第 4 节。

## 1. 一条命令的顺序

```bash
export IDIOLECT_CORPUS_DIR=/path/to/your/gold        # PowerShell: $env:IDIOLECT_CORPUS_DIR = "..."
export IDIOLECT_REPORT_DIR=data                      # 让「没有 --out」的三个脚本落到 data/

py -X utf8 tools/distill/scene_discover.py           # 场景原型（诊断：看你的语料能不能分出场景）
py -X utf8 tools/distill/validate_scenes.py          # 场景分离度 / 纯度（只出报告）
py -X utf8 tools/distill/export_targets.py           # → data/style_targets.json
py -X utf8 tools/distill/tic_profile.py              # → data/tic_profile.json
py -X utf8 tools/distill/tic_by_scene.py             # → data/tic_by_scene.json
py -X utf8 tools/distill/export_profiles.py           # → data/style_profiles.json（写 DATA，不受 REPORT_DIR 影响）
py -X utf8 tools/distill/scene_char_baseline.py --no-exemplars --out data/scene_char_baseline.json
py -X utf8 tools/distill/scene_stats.py         --no-exemplars --out data/scene_stats.json
py -X utf8 tools/distill/export_scene_targets.py     # → idiolect/scene_length_targets.py（包内，原位更新）
py -X utf8 tools/distill/export_profiles.py --check  # 校验已发布画像与当前语料一致
```

**参数支持不统一**（2026-09-13 逐个 `--help` 核过）：`export_targets` / `tic_profile` / `tic_by_scene` **没有 `--out`**，只能靠 `IDIOLECT_REPORT_DIR` 决定落点；`export_profiles` 直接写 `DATA`；带 `--out` 的只有 `scene_char_baseline` / `scene_stats` / `export_scene_targets`。后两个刻意用 `--out` 而不是切 `REPORT_DIR`，是为了不让 `.md` 伴随产物落进 `data/`。

六个 `data/*.json` 与 `idiolect/scene_length_targets.py` 就是全部产物。`data/README.md` 里登记了每个文件的生成命令与被谁消费——**改了生成方式就同步改那张表**。

## 2. 三条必须知道的口径

- **`style_targets.json` 不过滤 split**，所以它的 `n` 含留出行（`cn.anon.n = 1579`）；`style_profiles.json` 是 train-only（`n = 1244`）。这是刻意的差异，不是 bug。
- **发布形态由命令产出**：`scene_char_baseline` 与 `scene_stats` 的例句字段必须用 `--no-exemplars` 剥掉，不能手工编辑 JSON。
- **诊断类脚本不保证确定性**：`scene_discover` / `validate_scenes` / `scene_distill` 的并列项顺序不保证；但**发布数据必须可重建**——同一份语料跑两次，JSON 值与键序要逐字段一致。

## 3. 验收

```bash
py -X utf8 -m pytest tests -q                 # 137 项；含「发布画像无原文」与「跨进程确定性」
py -X utf8 tools/offline_smoke.py             # 数据形状 + 130 格覆盖 + 门禁 + 零写校验
```

逐条自查：

- [ ] `data/` 六个文件都非空，`scene_char_baseline.json` 的键数 = 角色数 × 场景数；`tic_by_scene.json` 的 cell 数也符合预期。
- [ ] `scene_length_targets.py` 的格子数与 `MIN_N` 丢弃数打印出来了（换语料后丢弃变多通常意味着某个场景样本不够）。
- [ ] `export_profiles.py --check` 返回 0。
- [ ] 同一份语料跑两遍，`data/` 的 JSON 值逐字段一致（不是比 `git diff` 是否为空——行尾可能差一字节）。
- [ ] `data/` 里最长的字符串仍是说明字段，没有整句台词。

## 4. 常见坑

- **空语料「成功」写出空产物**：所有读语料的脚本都必须先 `require_corpus()`（`tools/_paths.py`），它给出人话提示并 `SystemExit`，不写任何东西。
- **词表并列项**：`scene_stats` 的词表与 `logodds_signature` 的 top-N 都加了兜底排序（并列按词排）；自己新写的导出脚本要照做，否则哈希随机化会让两次运行产出不同的文件。
- **场景数变了**：通用场景与角色专属场景的**顺序不变量**在 `docs/03-features.md` 第 2.1 节，改场景体系要同时改 `scene_classifier._RULES` 与 `general_scenes`。

---

相关：[`docs/03-features.md`](../../../docs/03-features.md)（五类特征怎么算、落在哪）｜[`docs/04-evaluation.md`](../../../docs/04-evaluation.md) 第 9 节（可重建性）
