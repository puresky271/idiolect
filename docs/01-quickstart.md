# 快速开始

> 讲什么：从零跑通全链路——装包、看四层 prompt、体检、跑一次真探针、换成自己的语料。 ｜ 前置：Python 3.11+；跑探针需要一个 OpenAI 兼容端点。

## 你需要什么

- Python 3.11 或更高。Windows 上统一用 `py -X utf8` 启动，裸 `python` 可能解析到没装依赖的解释器。
- 想跑探针的话，一个 OpenAI 兼容的 API key（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）。
- 想重跑语料蒸馏的话，原作语料（本仓库不分发，见 `docs/02-corpus.md`）。

## 安装

只想用装配库（不碰工具链）的话，装成包最省事——运行时零第三方依赖：

```bash
pip install .
python -m idiolect list                                  # 五个示例角色
python -m idiolect prompt 乐奈 "你今天又想去哪找猫"       # 这句话此刻的完整 system prompt
python -m idiolect chat 乐奈 "你今天又想去哪找猫"         # 真聊一轮（需 openai 与 LLM_* 环境变量）
```

要跑仓库自带的工具链（门禁 / 探针 / 蒸馏），装依赖：

```bash
py -X utf8 -m pip install -r requirements.txt
```

只跑装配、门禁、冒烟不需要额外依赖。跑探针要装 `openai`，重算语料统计要装 `requirements-corpus.txt` 里的东西（含句向量模型，比较大）。

## 五分钟看明白它在干什么

```bash
# 1. 看某个人此刻的完整 prompt（四层，逐层字符数都打出来）
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"

# 2. 看「明天几点上课」这一轮，五个人的 prompt 差在哪
py -X utf8 tools/gates/dump_prompt.py --all --matrix
```

产物在 `report/`：`prompt_ran_a_after_msg.txt` 是分层审计版，`.json` 是最终 messages 数组。第 1 条命令里乐奈的 `turn_logic` 层长度不为 0（命中「猫」这个话题），第 2 条里 `plain`（「在干嘛」）那一格的 `turn_logic` 为 0，因为那一轮没有命中任何场景。

## 验证仓库是健康的

```bash
py -X utf8 tools/offline_smoke.py
```

它不调模型，跑完会告诉你四层装配、场景覆盖、触发矩阵、内容红线、派生统计、门禁、单测是否通过，并且比对仓库文件指纹确认整轮检查没有写过任何文件（除 `report/`）。

## 跑一次真探针

```bash
# 1. 生成占位夹具（首次）
py -X utf8 tools/probe/make_fixtures.py

# 2. 干跑，确认装配生效（不调模型）
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1

# 3. 真跑：五角色 × 通用场景夹具 × 每格 3 次
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic \
    --registry --cats 通用场景 --runs 3

# 4. 打分 + 与原作同场景台词并排对照 + 复述审计
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
```

第 3 步需要 `LLM_API_KEY`。密钥来源见 `docs/05-tooling.md` 最后一节。

结果长什么样（一次真实运行，五角色 × 7 场景 × 3 次，共 105 条）：

| 角色 | fidelity | 硬规则 V 级 | 泄漏率 |
|---|---|---|---|
| 爱音 | 86.5 | 4.9% | 0% |
| 灯 | 79.9 | 0.0% | 0% |
| 立希 | 82.4 | 0.0% | 0% |
| 素世 | 85.4 | 0.0% | 0% |
| 乐奈 | 79.9 | 0.0% | 0% |

逐场景蒸馏分均值 0.466（35 格，每格 3 条），同格互异率 93/105，逐字复述率 1%、最长公共子串 3 字。这些数字的口径与读法见 `docs/04-evaluation.md`，**不要**把它们当成绝对分横向比较。

## 用你自己的语料

```bash
export IDIOLECT_CORPUS_DIR=/path/to/corpus     # Windows: $env:IDIOLECT_CORPUS_DIR = "..."
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/export_scene_targets.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_profiles.py
```

前三个产出写进 `data/`，会成为 prompt 里的数字与评分基线；第四个产出探针用的画像。语料缺失时探针退回读随仓库发布的画像，`[probe] gold 画像来源 = ...` 那行会说明用的是哪条路径。

## 接进你自己的角色系统

`idiolect/assemble.py` 是装配的唯一入口：

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")
```

`build_system_prompt` 返回四层拼好的 system 段，`build_messages` 再补 history 与本轮 user。真实系统可以在它前面接记忆、世界状态、日程，那些层与本仓库的方法无关，本仓库只负责「这个人怎么说话」。

## 目录

| 目录 | 内容 |
|---|---|
| `idiolect/` | 运行时：装配器、场景分类、场景引擎、五个角色包 |
| `data/` | 派生统计（不含原作文本） |
| `fixtures/` | 探针夹具占位（system 为空，配合 `--assemble` 使用） |
| `tools/corpus/` | 抓取与清洗 |
| `tools/distill/` | 蒸馏与导出 |
| `tools/probe/` | 探针 |
| `tools/score/` | 评分与审计 |
| `tools/gates/` | 机械门禁与 prompt diff |
| `docs/` | 方法论文档集（00 总纲 → 07 turn_logic 与后处理） |
| `report/` | 所有产物（gitignored） |

## 验证过什么

- `pytest tests`：107 项通过，1 项跳过（需要语料）。
- `tools/offline_smoke.py`：装配、场景覆盖、触发矩阵、内容红线、派生统计、四道门禁、零写校验全部通过。
- 57 个脚本逐个 `--help`：无 import 或语法失败；其中 15 个需要语料的脚本用真实语料实跑过一遍。
- 一次真实探针：5 角色 × 7 场景 × 3 次 = 105 条回复（数字见 README）。
- 把仓库克隆到空目录后重跑：`pytest`、`offline_smoke`、探针 dry-run 均通过，不需要任何环境变量。
- 发布数据可重建：用金标准 cn 语料重跑六条生成命令，`data/` 六个文件与发布版本逐字节相同。

---

**上一站**：[`00-methodology.md`](00-methodology.md) ｜ **下一站**：[`02-corpus.md`](02-corpus.md) ｜ **索引**：[`README.md`](README.md)
