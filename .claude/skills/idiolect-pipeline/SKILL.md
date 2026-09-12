---
name: idiolect-pipeline
description: "Orchestrate the whole idiolect pipeline for a cast of your own: your corpus in, a working four-layer prompt plus evaluation artifacts out. Use this skill whenever the user wants to apply idiolect to characters other than the shipped five, asks what the full pipeline is or in what order to run things, wants a checklist from corpus to published derived statistics, or asks which parts are automatic and which have to be authored by hand. Chains the four stage skills (idiolect-corpus, idiolect-distill, idiolect-cast, idiolect-evaluate) with the gate that must pass after each stage, and states plainly what the repository does not automate."
---

# idiolect-pipeline：从别人的语料到自己的产物

一句话：**你带来语料，这条管道给你一套可运行的约束 + 可复核的评测证据。**

```
① 语料          ② 蒸馏                ③ 角色包              ④ 评测
你的台词集  →  派生统计（data/）  →  四层 prompt 可跑  →  probe + 分数 + 门禁证据
   │                │                     │                    │
   └ 格式与切分     └ 可重建性            └ 两条文字红线        └ n=6 不下结论
```

四步各自是一个 skill，本文只讲**顺序、交接物和验收**。

## 交接物（每一步必须产出的东西）

| 阶段 | skill | 产物 | 通过条件 |
|---|---|---|---|
| ① 语料 | [`idiolect-corpus`](../idiolect-corpus/SKILL.md) | `$IDIOLECT_CORPUS_DIR/{lang}.jsonl` + `gold_stats.json` | 行数/切分数非零；质检表看过；角色 key 表已改齐 |
| ② 蒸馏 | [`idiolect-distill`](../idiolect-distill/SKILL.md) | `data/` 六个 JSON + `idiolect/scene_length_targets.py` | 格数符合预期；`export_profiles.py --check` 返回 0；跑两遍逐字段一致 |
| ③ 角色包 | [`idiolect-cast`](../idiolect-cast/SKILL.md) | `idiolect/characters/<key>/` 五个文件 + registry 注册 | 五个门禁全绿；`dump_prompt --all --matrix` 逐份看过 |
| ④ 评测 | [`idiolect-evaluate`](../idiolect-evaluate/SKILL.md) | `report/probe_*.jsonl` + 四件套报告 + 两臂 dump | 池化后才下结论；copy audit 与 repeat rate 一起看 |

## 一次完整跑通的命令序

```bash
# 0. 环境
py -X utf8 -m pip install -r requirements.txt

# 1. 语料（示例：用自己的目录）
export IDIOLECT_CORPUS_DIR=/path/to/your/gold          # PowerShell: $env:IDIOLECT_CORPUS_DIR = "..."
py -X utf8 tools/corpus/build_gold.py
py -X utf8 tools/corpus/audit_corpus_quality.py

# 2. 蒸馏（注意：export_targets / tic_profile / tic_by_scene 没有 --out，靠 REPORT_DIR 落点）
export IDIOLECT_REPORT_DIR=data                        # PowerShell: $env:IDIOLECT_REPORT_DIR = "data"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/tic_profile.py
py -X utf8 tools/distill/tic_by_scene.py
py -X utf8 tools/distill/export_profiles.py            # 写 DATA，不受 REPORT_DIR 影响
py -X utf8 tools/distill/scene_char_baseline.py --no-exemplars --out data/scene_char_baseline.json
py -X utf8 tools/distill/scene_stats.py --no-exemplars --out data/scene_stats.json
py -X utf8 tools/distill/export_scene_targets.py       # → idiolect/scene_length_targets.py

# 3. 角色包（手写 canon/voice/turn_logic）之后
py -X utf8 tools/gates/audit_role_packages.py
py -X utf8 tools/gates/voice_meta_gate.py
py -X utf8 tools/offline_smoke.py

# 4. 评测
py -X utf8 tools/probe/make_fixtures.py
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --cats 通用场景 --runs 3
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
```

每一步之间都要过门禁：**门禁不过就别往下走**。`tools/offline_smoke.py` 是总闸，它会在一次运行里把装配、场景覆盖、触发矩阵、内容红线、数据形状、四道门禁、单测和零写校验全跑一遍。

## 哪些是自动的，哪些必须人写

| 自动（从语料算） | 人写（语料给不出） |
|---|---|
| 场景体系与长度目标（130 格） | **canon 长档案**：这个人是谁 |
| 风格画像、口癖、场景口癖、话题词表 | **voice manifest**：句式、关系差异、反模板约束 |
| 场景基线与评分参照系 | **场景模块正文**：这一轮该怎么说话 |
| 四层里的 `style_target` 与 `turn_logic` 的数字 | `turn_logic` 的**触发词取舍**（要用 `verify_triggers.py` 拿语料实证） |

语料是游戏活动剧情的快照，**日常道具天然缺席**：`data/` 里没覆盖不等于 canon 里不该有。反过来，凭感觉加的触发词会被门禁打回。

## 换成别的作品要动的地方

这套运行时是围绕五个角色搭的，角色表分布在多个文件里。换 cast 的第一件事是把它们找齐：

```bash
git grep -l '"tomori"' -- tools idiolect        # 当前 28 个文件
```

必须改的表列在 [`idiolect-corpus`](../idiolect-corpus/SKILL.md) 第 1 节。改完用 `offline_smoke.py` 收口——它的「装配.四层齐全」和「场景.长度目标覆盖」会直接点名缺谁。

## 已知边界（先讲清楚，省得走到一半才发现）

- **评分是相对量**：`scene_distill` / fidelity 只在同批次内做 before/after 比较，换模型、换夹具、换时钟就不可比。
- **单臂每格 6 条不下结论**：要池化多臂，并用 `power_calc.py` 看样本量。
- **夹具的可测性**：需要上文指代的场景（「你刚才那句什么意思」）用占位夹具测不出来。
- **词面通道对单个汉字失明**：见 [`docs/08-context-workspace.md`](../../../docs/08-context-workspace.md) 第 4 节。
- **语料不入库**：`raw/` 与 `*.jsonl` 已被 `.gitignore` 排除；发布形态只有聚合量。

---

相关：总纲 [`docs/00-methodology.md`](../../../docs/00-methodology.md)｜阅读路径 [`docs/README.md`](../../../docs/README.md)｜失败名录 [`docs/06-lessons.md`](../../../docs/06-lessons.md)
