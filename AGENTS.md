# AGENTS.md

> 给 AI 编码代理的项目说明。本文描述的是仓库实际内容，读者无需任何背景知识。

## 项目概览

**idiolect**（个人语型）：让 AI 说话像《BanG Dream! It's MyGO!!!!!》的五个角色（爱音、灯、立希、素世、乐奈），并且能**用数据证明「真的变像了」**。

方法：从原作台词里蒸馏可检验的风格特征（长度、句数、口癖、称呼、场景分类），把它们落成 system prompt，再用探针与机械门禁验证效果。**不做微调，不分发原作文本**——仓库只发布派生统计量（`data/` 下的聚合 JSON）。

核心入口：

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")
```

装配出四层 prompt，顺序固定（稳定前缀在前，动态块在后）：

| 层 | 内容 | 变化频率 |
|---|---|---|
| `canon` | 角色长档案 | 静态 |
| `voice` | 语气 manifest：句式、口癖、关系差异、反模板化硬约束 | 静态 |
| `style_target` | 说话尺度：字数/句数/句末/自称的可检验数字，命中场景时换成该场景的数字 | 每轮 |
| `turn_logic` | 本轮场景/主题指引，只在命中时注入 | 每轮 |

文档在 `docs/`（索引与阅读路径见 `docs/README.md`）：`00-methodology.md`（方法总纲）、`01-quickstart.md`、`02-corpus.md`（语料）、`03-features.md`（特征）、`04-evaluation.md`（指标口径）、`05-tooling.md`（工具手册，最实用）、`06-lessons.md`（踩坑清单）、`07-turn-logic-and-postprocessing.md`、`08-context-workspace.md`（四层在真实系统里的前后文）。

## 技术栈与运行环境

- 纯 Python 3.11+，有 `pyproject.toml`（`pip install .` 可装，`idiolect` 运行时零第三方依赖；CLI 入口 `python -m idiolect`）。CI 是 GitHub Actions（`.github/workflows/ci.yml`：离线 smoke 矩阵 + wheel 包数据校验）。测试通过 `conftest.py` 把仓库根挂上 `sys.path`（直接 `import idiolect.*`）。
- 依赖见 `requirements.txt`：`openai`、`numpy`、`jieba`、`requests`、`pytest`。重算语料派生统计才需要 `requirements-corpus.txt`（`sentence-transformers`、`scikit-learn`，模型权重首次运行时下载）。
- **Windows 上统一用 `py -X utf8`** 跑脚本；裸 `python` 可能解析到没装依赖的解释器。所有命令在仓库根目录执行。

## 目录与模块划分

```text
idiolect/            # 运行时包：把特征写成 prompt 约束
  assemble.py        #   四层装配器（核心入口，build_messages / build_system_prompt）
  registry.py        #   角色名 → 角色包的唯一分发点（含别名归一化）
  scene_classifier.py / scene_engine.py / general_scenes.py   # 场景分类与动态注入；scene_engine 另托管 turn_logic 共享脚手架（SessionStore 去重表 / env 假值表 / 深模块执行器）
  style_target.py / scene_length_targets.py                   # 长度/句数目标块
  workspace.py       #   上下文工作区（12 层装配 + 事实选择器），四层之外的骨架
  facts.py / tone.py / _text_rng.py   # 事实选择器 / 语气分类 / 文本定种 RNG（后处理随机步骤的确定性）
  characters/<key>/  #   五个角色包（anon/tomori/taki/soyo/rana）：
                     #     api.py（对外窄入口）、canon.py、voice.py、
                     #     turn_logic/（场景模块；其中的纯数据目录已迁 data/*.json，
                     #       经 importlib.resources 读取）、voice_check/（出站清洗）
tools/               # 工具链，按职责分子目录
  _paths.py          #   路径与环境变量的唯一实现，脚本不许自己拼路径
  offline_smoke.py   #   一条命令健康检查（不调 LLM，可进 CI）
  mock_clock.py      #   评测时钟
  secrets_loader.py  #   密钥加载
  distill/           #   从语料统计派生量（export_targets / tic_profile / scene_char_baseline …）
  gates/             #   机械门禁（dump_prompt、voice_meta_gate、_tl_deep_check …）
  probe/             #   探针（make_fixtures、probe_runner、prompt_patch …）
  score/             #   评分（probe_report、scene_distill、_copy_audit、power_calc …）
  corpus/            #   语料抓取与构建（需要 IDIOLECT_CORPUS_DIR）
data/                # 随仓库发布的派生统计（无原作文本），每个文件的生成脚本见 data/README.md
fixtures/            # 探针夹具（messages_<角色>.json；占位夹具 system 为空）
raw/gold/            # 语料默认位置（仓库不带语料）
report/              # 所有工具产物的默认输出目录
tests/               # pytest 单测
bootstrap.py         # 一条命令装成可跑状态（建 .venv → 装依赖 → 自检 → 打印一份 prompt）
.claude/skills/      # 给 agent 的流水线 skill（见下）
.github/workflows/   # CI（离线 smoke 矩阵 + wheel 包数据校验）
```

**访问角色包只走 `idiolect/registry.py`**（`get_canon_profile` / `get_voice_manifest` / `render_turn_special_block`），不要按角色名堆 if/elif，也不要直接 `import idiolect.characters.<key>.*`。名字表（含日文写法、简繁差异、常见误写）也只有 `registry._ALIASES` 一份，角色包里的 `is_<char>()` 问它，别自带名单。

## 流水线 skill（`.claude/skills/`）

五个 skill 把「换成别的角色」这件事拆成阶段，每个都带命令与验收条件；agent 会自动加载，人也可以当操作手册读：

| skill | 阶段 |
|---|---|
| `idiolect-corpus` | 语料：格式、切分、角色 key 决策、要跟着改的表清单 |
| `idiolect-distill` | 蒸馏：`data/` 六个 JSON + `scene_length_targets.py` |
| `idiolect-cast` | 角色包：canon/voice/turn_logic/voice_check + 注册 + 门禁 |
| `idiolect-evaluate` | 评测：probe、四件套、池化、功效、两臂 dump |
| `idiolect-pipeline` | 编排：交接物、每段门禁、自动／人写对照表 |

## 构建与测试命令

```bash
python bootstrap.py                        # 一条命令：建 .venv + 装依赖 + 自检 + 打印 prompt
python bootstrap.py --no-tools             # 只要装配库（运行时零第三方依赖）
python bootstrap.py --skip-smoke           # 跳过自检

py -X utf8 -m pip install -r requirements.txt

# 健康检查（最常用，零 LLM、零写仓库文件）
py -X utf8 tools/offline_smoke.py          # 全套：装配 + 红线 + 数据 + 门禁 + 单测 + 零写校验
py -X utf8 tools/offline_smoke.py --fast   # 跳过门禁与单测，一秒出结果

# 单测
py -X utf8 -m pytest tests/

# 查看某角色某句话的完整 prompt（不需要密钥和语料）
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"
py -X utf8 tools/gates/dump_prompt.py --all --matrix

# 跑探针（需要 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）
py -X utf8 tools/probe/make_fixtures.py
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景

# 用自己的语料重算派生统计
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/export_profiles.py --check   # 校验已发布画像与语料一致
```

装了包之后还有一个 `idiolect` 命令（`[project.scripts]`），等于 `python -m idiolect`；`uvx --from git+https://github.com/puresky271/idiolect idiolect prompt Rana "…"` 可以不 clone 直接跑。

改动后至少跑 `py -X utf8 tools/offline_smoke.py --fast`；改 prompt 相关代码跑全套 smoke。

## 代码与协作约定

- **注释与文档用简体中文**；模块 docstring 通常先写「这是什么、为什么」。
- **评测时钟**：任何读「现在」的代码从 `tools/mock_clock.py` 的 `mock_now()` 取，不要直接 `datetime.now()`。默认固定在 `2026-09-12T15:00:00+09:00`；用真实时钟跑出的批次数字不可与 mock 批次比较。
- **路径**：只用 `tools/_paths.py`（环境变量：`IDIOLECT_CORPUS_DIR`、`IDIOLECT_REPORT_DIR`、`IDIOLECT_DATA_DIR`）。
- **产物纪律**：脚本产物写 `report/`；`offline_smoke` 自带零写校验，除 `report/` 外改动任何仓库文件都会 FAIL。
- **改 prompt 必须留证据**：用 `dump_prompt.py --phase before/after` 留两臂 diff。
- **静默失效比报错危险**：写文件的脚本要有零结果守卫（参考 `build_gold.py`、`export_scene_targets.py`）；读语料的脚本对空文件直接退出。
- 加一个角色或场景的完整步骤见 `docs/05-tooling.md` 第 9 节（建包 → 注册 `_PACKAGE_NAMES`/`_ALIASES` → 保持 `general_scenes.py` 与 `scene_classifier.py` 的 `_RULES` 顺序一致 → 跑 smoke → 留 diff）。

## 测试策略

- `tests/` 下是 pytest（`unittest` 风格类），分六类契约测试，每条断言对应真实踩过的坑：
  - `test_tooling_contracts.py`：mock 时钟、装配完整性、`--assemble` 不被覆盖、元叙述门禁覆盖面；
  - `test_scene_turn_logic.py` / `test_soyo_rana_deep_turn_logic.py`：触发器命中正确且不过宽、per-session 去重、角色隔离与 env 回退开关、触发词有语料实证；
  - `test_workspace.py`：上下文层序固定、pinned 层不被预算裁掉、执行包贴最后一条 user、事实选择器的阈值与双预算；
  - `test_scene_engine_scaffold.py`：turn_logic 共享脚手架（SessionStore 的 mark/has/reset 与 LRU 淘汰、env 假值表、深模块执行器）；
  - `test_voice_check_wiring.py`：tomori/taki/anon 后处理真的接线（不再是 stub）、清洗确定性（按输入定种）、`<CHAR>_VOICE_CHECK_ENABLED` 总开关与非本角色透传；
  - `test_score_golden.py`：评分链 golden 文件（scene_distill / _pool_arms 全量输出、probe_report 编排契约；golden 由测试内的合成输入离线复现，失配先确认是预期改动再重新生成，不要手改）。
- 新增约束时**先写契约测试再改实现**；触发词必须能拿出语料实证（`tools/distill/verify_triggers.py`）。
- `tools/offline_smoke.py` 是总闸，会跑门禁与单测，适合当作提交前检查。

## 安全与合规红线

- **不分发原作文本**。`data/` 只能是聚合统计（字数分布、频次、分位数）；基线文件发布前必须剥掉例句（`--no-exemplars`）。`offline_smoke` 与单测各有一道检查盯着这条线。
- **角色可见文本里不许有元叙述**。「语料」「实测」「中位」「频次」「基线」这类词进了 prompt，模型会顺着谈自己的设定。`tools/gates/voice_meta_gate.py` 扫 canon / voice / style_target / turn_logic 四个面，改任何 prompt 文本后必须过这道门禁。
- **密钥不入库**：探针按 进程环境变量 → 仓库根 `.env` → `.streamlit/secrets.toml` 的顺序取 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（见 `tools/secrets_loader.py`）。
- 角色与作品权利属于 Bushiroad / Craft Egg 及相关权利方，本项目与权利方无关，见 `NOTICE.md`；代码以 MIT 发布。
- 指标（蒸馏分、fidelity）是**相对量**，只用于同批次 before/after 比较；换模型、换夹具、换时钟后跨批次不可比。
