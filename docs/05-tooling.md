# 工具手册

> 讲什么：工具手册——每个脚本干什么、怎么调，含「加一个角色 / 加一个场景」的完整步骤。 ｜ 前置：无；找命令时直接来这篇。

**目录**：[1 路径与环境变量](#1-路径与环境变量) ｜ [2 一条命令的健康检查](#2-一条命令的健康检查) ｜ [3 mock 时钟](#3-mock-时钟) ｜ [4 全量 prompt dump](#4-全量-prompt-dump) ｜ [5 探针](#5-探针) ｜ [6 评分四件套](#6-评分四件套) ｜ [7 机械门禁](#7-机械门禁) ｜ [8 语料与蒸馏](#8-语料与蒸馏) ｜ [9 加一个角色或一个场景](#9-加一个角色或一个场景) ｜ [10 密钥](#10-密钥)

所有命令在仓库根跑，统一用 `py -X utf8`（Windows 上裸 `python` 可能解析到没装依赖的解释器）。产物默认写进 `report/`，可用 `IDIOLECT_REPORT_DIR` 改。

## 1. 路径与环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `IDIOLECT_CORPUS_DIR` | `raw/gold` | 语料目录。本仓库不带语料，要用蒸馏/重算脚本时指到自己的语料目录 |
| `IDIOLECT_REPORT_DIR` | `report` | 探针与评分产物 |
| `IDIOLECT_DATA_DIR` | `data` | 随仓库发布的派生统计 |
| `IDIOLECT_MOCK_NOW` | 未设置（= mock） | 覆盖评测时钟，见第 3 节 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | — | 探针与 `--with-llm` 才需要 |

路径解析只有一处实现：`tools/_paths.py`。任何脚本都不自己拼语料路径。

## 2. 一条命令的健康检查

```bash
py -X utf8 tools/offline_smoke.py          # 全套：装配 + 红线 + 数据 + 门禁 + 单测 + 零写校验
py -X utf8 tools/offline_smoke.py --fast   # 跳过门禁与单测，一秒出结果
py -X utf8 tools/offline_smoke.py --with-llm   # 额外每角色真调一次模型
```

它不调 LLM，所以能进 CI。检查项：四层装配齐全、层顺序、层预算、场景覆盖、turn_logic 触发矩阵、角色串味、内容红线扫描、夹具结构、派生统计形状、四道门禁、`tests/`，最后比对仓库文件指纹——除 `report/` 之外的任何文件被改动都会 FAIL。产物是 `report/offline_smoke.md`。

## 3. mock 时钟

```bash
py -X utf8 tools/mock_clock.py                              # 打印当前生效时间与来源
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00   # 打印要设的环境变量行
py -X utf8 tools/mock_clock.py --real                       # 同上，改用真实时钟（带警告）
```

`--set` / `--real` / `--shell` **只打印**那一行 `$env:IDIOLECT_MOCK_NOW = '...'`，不会改变当前 shell（子进程改不了父进程的环境）——把输出贴进 shell 才生效，命令自己也会再打印一次「当前生效」提醒你没变。

默认 `2026-09-12T15:00:00+09:00`。任何读「现在」的代码都从 `mock_clock.mock_now()` 取，不要直接 `datetime.now()`。探针启动时会打印时钟来源，检测到真实时钟会警告这批数字不可与 mock 批次比较。

## 4. 全量 prompt dump

```bash
# 单角色一句话
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"

# 五角色 × 四条会命中不同层的话
py -X utf8 tools/gates/dump_prompt.py --all --matrix

# prompt diff 门禁的两臂
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase before
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase after

# 只装某些层（排查哪一层在撑 prompt）
py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice

# 用门禁里的场景名
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --case general.comfort
```

产物三份：`prompt_<char>_<phase>_<label>.json`（最终 messages 数组，与探针喂给模型的对象逐字节相同）、`.txt`（分层审计版）、`.layers.json`（各层字符数）。另有一份 `prompt_dump_index_<phase>.json` 汇总本次所有 dump，用于两臂对比。

`--phase before` 把深模块与通用场景层的 env 回退开关全部置 0，得到「改动前行为」的那一臂。

## 5. 探针

```bash
# 生成占位夹具（首次）
py -X utf8 tools/probe/make_fixtures.py

# 干跑：不调 LLM，只验证夹具与装配
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1

# 正式跑：五角色 × 通用场景夹具 × 每格 3 次
py -X utf8 tools/probe/probe_runner.py --label repo_standalone --assemble --turn-logic \
    --registry --cats 通用场景 --runs 3
```

参数要点：

- `--assemble`：按本轮 user 现场装配四层 system。占位夹具的 system 为空，**不加这个参数测到的是没有角色 prompt 的模型**。装配结果若短于 1000 字符，脚本直接报错退出。
- `--turn-logic`：注入生产 turn_logic 块。没有它，探针测不到动态层。
- `--registry`：用统一场景注册表（含语料反推的夹具），每格带 scene key，评分才能按场景聚合。
- `--runs N`：每格生成次数。分布级指标需要 N ≥ 3，正常评测用 6。
- `--patch`：实验臂（`targets` 等），把数值目标块插到 persona card 末尾。生产现状用 `none`。
- `--thinking off|on`：关掉思考链换取可复现与低成本。注意开思考时大预算下仍会出现空 content 的样本，这类样本要计为无效而不是拒答。

夹具来源顺序：`fixtures/` 里最新的 `messages_<char>*.json`，再退到 `_offline_smoke_out/`。要换成自己的运行时 dump，把文件放进 `fixtures/` 即可。

另有两个专项探针（`--label` 产物可直接被 `oob_check` / `evidence_check` 的 `--label` 扫描，详见 `docs/04-evaluation.md` 第 13、14 节）：

```bash
py -X utf8 tools/probe/oob_probe.py --label oob1 --runs 2 --gate    # 越界拒答：7 维越界夹具 → 输出侧高危审计
py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate        # 多轮漂移：8 轮自对话，前后半段泊松检验
```

## 6. 评分四件套

```bash
py -X utf8 tools/score/probe_report.py --label repo_standalone --scenes crisis,comfort --cat 通用场景
```

一条命令跑完四步，产物全在 `report/`：

| 步骤 | 脚本 | 产物 |
|---|---|---|
| 分布级评分 | `scene_distill.py` | `scene_distill.md` / `scene_distill_<label>.json` |
| 逐场景对照 | `scene_feedback.py` | `scene_feedback_<scene>.md` |
| 同格重复度 | `_repeat_rate.py` | 控制台 + 报告 |
| 逐字复述审计 | `_copy_audit.py` | 控制台 + 报告 |

第五项**多臂池化**（`_pool_arms.py`）不在默认四步里，只有同时给了 `--off-labels` / `--on-labels` 两个臂才跑；单独调用见下。

单独的入口：

```bash
py -X utf8 tools/score/scene_distill.py --labels repo_standalone
py -X utf8 tools/score/scene_distill.py --labels repo_standalone \
    --baseline report/scene_char_baseline_holdout.json   # 验收轮：holdout 基线（样本外）
py -X utf8 tools/score/scene_feedback.py --scene comfort --labels repo_standalone --n 8
py -X utf8 tools/score/_copy_audit.py --cat 通用场景 --labels repo_standalone --detail
py -X utf8 tools/score/_pool_arms.py off_arm on_arm1,on_arm2,on_arm3
py -X utf8 tools/score/power_calc.py            # 功效：从探针输出实测单条 sd
py -X utf8 tools/score/power_audit.py           # 现有样本量够不够
```

探针汇总表的头号指标是 **composite**（风格 0.65 + 内容锚点 0.35），fidelity 是对照列——
单看 fidelity 会奖励助手腔（口径与依据见 `docs/04-evaluation.md` 第 2.1 节）。

验收与盲评（合并前的最后两道）：

```bash
py -X utf8 tools/gates/accept_check.py --before off_arm --after on_arm   # 多指标门禁：任一退化即 FAIL
py -X utf8 tools/score/ab_blind.py --a off_arm --b on_arm                # A/B 盲评出题（worksheet + key）
py -X utf8 tools/score/ab_blind.py --tally 答卷.json --key report/ab_blind_off_arm_vs_on_arm_key.json
py -X utf8 tools/score/ab_blind.py --a off_arm --b on_arm --llm          # LLM 判卷（正交参考，不进门禁）
```

指标口径与读法见 `docs/04-evaluation.md`。

## 7. 机械门禁

```bash
py -X utf8 tools/gates/voice_meta_gate.py          # 元叙述（canon / voice / 说话尺度 / turn_logic 四个面）
py -X utf8 tools/gates/_gen_scene_check.py         # 通用场景注入正文规范
py -X utf8 tools/gates/_tl_deep_check.py           # 深模块注入正文规范
py -X utf8 tools/gates/audit_role_packages.py      # 角色包结构与注册表一致性
py -X utf8 tools/gates/dump_turn_logic_gate.py --phase after    # 触发矩阵 + 归属标记 + 角色串味
py -X utf8 tools/gates/voice_check_diff_check.py   # 后处理清洗的前后差异
py -X utf8 tools/gates/oob_check.py                # 输出侧越界审计（无参=自检；--label 扫探针批次，--gate 判定）
py -X utf8 tools/gates/evidence_check.py           # 证据一致性：担当/学校/CRYCHIC/称呼（无参=自检）
```

`dump_turn_logic_gate.py --phase before` 只产基线，不判期望（回退开关全关时按定义什么都不触发）。

## 8. 语料与蒸馏

需要语料，先设 `IDIOLECT_CORPUS_DIR`。读语料的脚本都有一道前置检查：文件缺失抛 `FileNotFoundError`，文件**存在但为空**直接退出（空语料会算出空产物，宁可当场停）。

```bash
py -X utf8 tools/corpus/crawl_bestdori.py     # 抓取（网络）
py -X utf8 tools/corpus/prep_hf_corpus.py     # HF parquet → 中间层（--dry-run 可先看）
py -X utf8 tools/corpus/build_gold.py         # 合并 + 切分 → raw/gold/<lang>.jsonl
py -X utf8 tools/corpus/build_gold.py --dry-run   # 只看会合并出多少条
py -X utf8 tools/corpus/audit_corpus_quality.py

py -X utf8 tools/distill/analyze_corpus.py         # 全局画像
py -X utf8 tools/distill/export_targets.py         # -> report/style_targets.json（发布副本在 data/）
py -X utf8 tools/distill/export_scene_targets.py   # -> idiolect/scene_length_targets.py
py -X utf8 tools/distill/scene_char_baseline.py    # -> report/scene_char_baseline.json
py -X utf8 tools/distill/scene_char_baseline.py --split holdout --no-exemplars
                                                   # -> report/scene_char_baseline_holdout.json（验收专用）
py -X utf8 tools/distill/scene_stats.py            # -> report/scene_stats.json
py -X utf8 tools/distill/tic_profile.py            # -> report/tic_profile.json
py -X utf8 tools/distill/tic_by_scene.py           # -> report/tic_by_scene.json
py -X utf8 tools/distill/export_profiles.py        # -> data/style_profiles.json（评分用画像）
py -X utf8 tools/distill/export_profiles.py --check # 校验已发布画像与语料是否一致
```

写成 `report/` 的产物要进 `data/` 时用发布形态（剥掉例句）：

```bash
py -X utf8 tools/distill/scene_char_baseline.py --no-exemplars --out data/scene_char_baseline.json
py -X utf8 tools/distill/scene_stats.py        --no-exemplars --out data/scene_stats.json
```

`export_profiles.py` 的产物是探针评分用的 gold 画像。语料不在时，探针自动退回读这份发布画像，`[probe] gold 画像来源 = ...` 那行会写清用的是哪条路径。

三个写文件的脚本带零结果守卫，防止误调用把已有的好数据覆盖成空：`build_gold.py`（没有源文件时拒绝写，除非 `--force-empty`）、`prep_hf_corpus.py`、`export_scene_targets.py`。

## 9. 加一个角色或一个场景

1. 在 `idiolect/characters/<key>/` 建包，至少提供 `get_canon_profile()`、`get_voice_manifest()`、`render_supplemental_blocks()`。
2. 在 `idiolect/registry.py` 的 `_PACKAGE_NAMES` 与 `_ALIASES` 注册角色名与别名。
3. 通用场景加在 `idiolect/general_scenes.py`，顺序必须与 `idiolect/scene_classifier.py` 的 `_RULES` 一致。
4. 跑 `py -X utf8 tools/offline_smoke.py`：装配、触发矩阵、红线、门禁会一起告诉你漏了什么。
5. 改动用 `dump_prompt.py --phase before/after` 留 diff。

## 10. 密钥

探针按顺序取 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`：进程环境变量优先，其次仓库根的 `.env`，最后 `.streamlit/secrets.toml`（顺序实现见 `tools/secrets_loader.py`）。三者都不入库。

---

**上一站**：[`04-evaluation.md`](04-evaluation.md) ｜ **下一站**：[`06-lessons.md`](06-lessons.md) ｜ **索引**：[`README.md`](README.md)
