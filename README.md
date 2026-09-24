<p align="center">
  <a href="./README.en.md">English</a> · <a href="./README.ja.md">日本語</a> · <strong>简体中文</strong>
</p>

<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="idiolect：让 AI 说话像角色，并且能证明它变像了。配图是《BanG Dream! It's MyGO!!!!!》五名成员——爱音、灯、立希、素世、乐奈——的插画。">
</p>

<h1 align="center">idiolect（个人语型）</h1>

<p align="center">
  <strong>让 AI 扮演角色时说话像本人，再用可复现的评测检查它是不是真的更像了。</strong>
</p>

<p align="center">
  <sub>~~Rikki，为什么你抱着吉他——是因为作者太懒，不想再重跑一张图吗~~</sub>
</p>

<p align="center">
  <a href="https://github.com/puresky271/idiolect/actions/workflows/ci.yml"><img src="https://github.com/puresky271/idiolect/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/runtime%20deps-0-brightgreen" alt="runtime dependencies: 0">
</p>

<p align="center">
  <a href="#-拿到手能做什么">拿到手能做什么</a> ·
  <a href="#看一段演示再检查证据">看一段演示</a> ·
  <a href="#-快速跑起来">快速跑起来</a> ·
  <a href="#-四层装配prompt-是怎么拼的">四层装配</a> ·
  <a href="#-文档">文档</a>
</p>

孩子们，随着现在的厂商越来越追求model在coding和agent方面的能力，我们的AI RP真是越来越难绷了啊，本仓库是基于作者的部分经验总结出来的一份“AI 角色扮演对话系统的评测方法学 + prompt 工程踩坑实录”，外加一套可复用的约束框架，希望能帮到想做AI角色的同好们。

用通用模型扮演角色，聊着聊着就会滑向同一副客服腔：话越说越长、动不动来一句「你的感受我完全能理解」、结尾还要升华一下，然后稳稳地接住你。本仓库的做法反过来：先从角色原本的台词里**量出 ta 说话的习惯**——一句话多长、一次说几句、爱用什么口头禅、什么场合说什么话——再把这些数字写成 prompt 里的硬约束，最后用自动检查验证「这次是不是真的更像了」。不做微调，仓库里也没有原作台词，只有统计出来的数字。

为了让方法看得见摸得着，全程拿《BanG Dream! It's MyGO!!!!!》的五名成员做**示例角色**。**方法可以迁移到别的作品**，但角色资料、语料基线和验证场景都得重建；这里只解决一件事——怎么证明「说话像」，并且把它做成一套独立、可复现的流程。

> [!IMPORTANT]
> **先把权利与许可说清楚**
> **代码**（`idiolect/`、`tools/`、`docs/`、`tests/`）以 MIT 发布，随便用（[`LICENSE`](LICENSE)）。
> **角色与作品不属于本仓库**：MyGO!!!!! 的角色、设定、剧情与音乐的权利归 **Bushiroad / Craft Egg 及相关权利方**。这是一个**非官方同人技术项目**，与权利方没有关联，也未获授权或背书。
> **仓库不含任何原作文本**（剧本、台词、歌词）与音频，`data/` 里只有统计出来的聚合数字；示例插画属于同人性质的使用，不是官方素材。
> 完整说明见 [`NOTICE.md`](NOTICE.md) 与文末的[版权、许可与免责](#-版权许可与免责)。

## 📦 拿到手能做什么

| 你能拿到 | 具体是什么 |
|---|---|
| **一个能直接用的装配库** | `pip install .` 之后 `from idiolect.assemble import build_messages` 就能拿到四层 prompt。**运行时零第三方依赖**（探针与蒸馏才需要 openai / numpy / jieba） |
| **一套能证明「更像了」的评测** | 探针 →（分布贴合 / 同格重复 / 逐字复述）三件套 → 多臂池化 → 功效估算；另有越界拒答与多轮漂移两个专项探针，加上事实一致性门禁。下面那张表就是一次真跑的 105 条回复 |
| **六道机械门禁 + prompt diff 门禁** | 改 prompt 不能只靠手感：`offline_smoke.py` 一条命令跑完装配、场景覆盖、触发矩阵、内容红线、数据形状、门禁与零写校验 |
| **可换作品的工具链** | 67 个脚本：抓取清洗、语料切分、场景发现、口癖蒸馏、长度目标导出、探针与评分。方法不绑作品，换角色只需重跑 |
| **现成的角色数据（只有聚合量）** | 26 个场景（13 通用 + 13 角色专属）、130 个「角色 × 场景」长度目标、114 格场景口癖、五个角色的风格画像 |
| **九篇方法论文档** | 语料怎么来、五类特征怎么算怎么落地、怎么评测、踩过哪些坑，各自独立可读 |

### 给 Agent 的展示层 Skill

把 [`skills/mygo-five-roleplay/`](skills/mygo-five-roleplay/SKILL.md) 整个目录交给 Claude/Codex，就能选五人之一直接对话，不需要 API key，也不需要 Python。角色资料随包携带，按选择加载；只保留需要的角色子目录也可以。说「用灯和我聊聊今天的排练」即可开始，说「退出」恢复成普通助手。

Skill 的静态资料与库同源，但不执行 Python 侧的动态路由、会话去重与后处理，所以体验好不等于评测过关。评测、蒸馏与门禁仍然是主线。安装、重新导出与校验见[快速开始](docs/01-quickstart.md#先体验五人-skill)。

建议的体验顺序：先用 Skill 感受同一个问题下五人的差别，再跑 `py -X utf8 tools/gates/dump_prompt.py --all --matrix` 看差别出自哪一层，最后用 `py -X utf8 tools/score/probe_report.py --label <label> --scenes crisis,comfort` 回到可复核的评测结果。

### 看一段演示，再检查证据

[![Claude Code 原生彩色终端实录：乐奈对话](assets/readme/roleplay-demo.gif)](assets/readme/roleplay-demo.mp4)

**[播放 / 下载短片](assets/readme/roleplay-demo.mp4)** · [静态预览](assets/readme/roleplay-poster.png) · [对话原文与来源说明](assets/readme/roleplay-transcript.json)

这段 **25 秒**视频直接录自 Windows Terminal 里的 **Claude Code**，保留原生配色，展示乐奈的一轮真实回复，本次模型为 **DeepSeek-v4-pro[1m]**。只裁掉了首尾的空闲片段，生成过程没有加速。Skill 与乐奈的资料已显式加载，输入作为启动消息提交；这段视频不验证 Skill 的自动发现，也不验证多轮稳定性。其余四人同样可以在 Skill 里选择。

![离线评测页：批次筛选、缺失条件提示与角色指标](assets/readme/evaluation-overview.png)

评测概览会保留历史批次里缺失条件的提示。下面展开乐奈的 comfort 场景，可以直接对照模型原文与清洗结果；旧记录里没保存的输入仍显示为未知。

![乐奈 comfort 场景：场景诊断与逐条原始、清洗后回复](assets/readme/evaluation-evidence.png)

在自己的批次上跑 `py -X utf8 tools/score/report_html.py --labels <label>`，打开生成的 `report/evaluation.html` 就能筛选并展开证据。截图来自历史 `repo_standalone` 批次，与上面的宿主体验是两次不同的实验。详见[评测指南](docs/04-evaluation.md)。

## 🚀 快速跑起来

**先拿到手——四条路，选一条就行：**

| 方式 | 一条命令 | 说明 |
|---|---|---|
| **让 agent 来做** | 把下面那段提示词贴给你的 coding agent | 最省事：它自己 clone、装依赖、跑自检 |
| **uv（一行、零残留）** | `uvx --from git+https://github.com/puresky271/idiolect idiolect prompt Rana "你今天又想去哪找猫"` | 立刻看 prompt；不 clone、不建环境 |
| **pip 装成库** | `pip install git+https://github.com/puresky271/idiolect` | 当依赖用；运行时零第三方依赖 |
| **只要文件** | `npx degit puresky271/idiolect idiolect` 或 `git clone --depth 1 https://github.com/puresky271/idiolect` | 要跑工具链、要读源码 |

给 agent 的提示词（Claude Code / Codex 之类都行）：

> 帮我跑通 https://github.com/puresky271/idiolect ：克隆下来、读 `AGENTS.md`、执行 `python bootstrap.py`，然后把自检结果和五个角色的完整 prompt 贴给我（`py -X utf8 tools/gates/dump_prompt.py --all --matrix`）。之后我要换成我自己的角色，按 `.claude/skills/idiolect-pipeline/` 的流程走。

**拿到之后**，在仓库根目录执行（需要 Python 3.11+）：

```bash
pip install .                                        # 运行时零第三方依赖
python -m idiolect list                              # 看看有哪几个角色
python -m idiolect prompt 乐奈 "你今天又想去哪找猫"     # 这句话此刻的完整 system prompt
python -m idiolect showcase "我今天有点撑不住了"        # 五人并排展示（不调用模型）
python -m idiolect chat 乐奈 "你今天又想去哪找猫"       # 真聊一轮（环境变量见下方）
```

想把工具链也备好，一条命令就够（建 `.venv`、装依赖、跑 `offline_smoke` 自检、打印某个角色的分层字数）：

```bash
python bootstrap.py
```

Windows 上建议把 `python` 换成 `py -X utf8`（裸 `python` 有可能解析到没装依赖的解释器）。`chat` 命令可以走任何 OpenAI 兼容端点：先设 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 三个环境变量，再 `pip install "idiolect[llm]"`。

在代码里调用：

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")   # 可直接发给模型的 messages 数组
```

## 🔍 示例角色的样本分析

以 MyGO!!!!! 这五个人为例：

| 角色 | 一句话通常多长（中位数） | 平均说几句 | 标志性习惯 |
|---|---|---|---|
| 爱音 | 20 字 | 1.6 句 | 35% 的话带感叹号，口癖「啊、诶、哦」 |
| 灯 | 11 字 | 1.2 句 | 81% 的话带省略号，一串串「······」 |
| 立希 | 15 字 | 1.4 句 | 短促直接，原作 39% 的话以名词直接起手 |
| 素世 | 16 字 | 1.4 句 | 温柔克制，感叹率只有 6% |
| 乐奈 | 6 字 | 1.2 句 | 极短，感叹率 3%，话题经常被猫带走 |

表里的中位数、句数与感叹号、省略号占比都能在 [`data/style_profiles.json`](data/style_profiles.json) 里逐条查到；立希那行的「名词起手」是语料口径下的统计，用 `tools/score/_noun_initial.py <批次名>` 能把它和原作基线一起打出来。

同一场景下差别还会放大：比如「被表白」这个场景，乐奈说 7 个字，素世在同一场景说 17 个字。这正是约束必须写成「这个角色 × 这个场合」的理由——不能让所有人共用一个平均数。

## ❓ 为什么需要它

模型扮演角色时会稳定地犯四个毛病——这不需要模型出错，它们本来就是训练目标的产物：

1. **回复变长**：角色原作里说 7 个字的场合，模型能写 700 字。
2. **套用共情模板**：「你的感受我完全能理解，当压力像潮水般涌来……」
3. **结尾升华**：每段对话都要收一个有意义又很正的尾。
4. **说漏嘴**：谈起自己的设定，把内心独白、思考标签直接说出来。

如果五个人安慰你时输出的是同一段话，角色之间就没有区别了。所以这套方法可以概括成一句：**把「像不像」变成几个能测量的数字，然后对着数字改**。

- **只和「同角色 × 同场景」的原作台词比**。不和「人通常怎么说话」比，也不和「这个角色的全局平均」比。
- **数字只负责报警，不负责定罪**。灯的输出比参照长 5 倍，一半原因是她的省略号也计入字数——到底算不算问题，得读回复才知道。
- **样本不够就说「没结论」**。每格只有 6 条样本时，同一场景同一 prompt，乐奈的贴合分能从 0.551 摆到 0.350，比要测的效应还大。
- **角色能看到的文字里，不许出现「语料」「中位数」「基线」这类词**。模型看见它们，有概率顺着聊起自己的设定。

完整方法见 [`docs/00-methodology.md`](docs/00-methodology.md)。

## 📊 历史探针批次（仅作定性示例）

下面这张表是一次真实探针（probe）的结果，不是设计目标。所谓探针，就是给五个角色各发一批话，把回复收回来逐项打分：

```bash
py -X utf8 tools/probe/probe_runner.py --label repo_standalone \
    --assemble --turn-logic --registry --cats 通用场景 --runs 3
py -X utf8 tools/score/probe_report.py --label repo_standalone --scenes crisis,comfort --cat 通用场景
```

| 角色 | 回复数 | composite（像不像，100 分制） | fidelity（风格贴合，对照列） | 踩红线比例 | 说漏嘴比例 | 场景贴合分 |
|---|---|---|---|---|---|---|
| 爱音 | 21 | 64.6 | 86.5 | 4.9% | 0% | 0.545 |
| 素世 | 21 | 90.5 | 85.4 | 0.0% | 0% | 0.532 |
| 立希 | 21 | 75.6 | 82.4 | 0.0% | 0% | 0.386 |
| 灯 | 21 | 86.9 | 79.9 | 0.0% | 0% | 0.365 |
| 乐奈 | 21 | 86.9 | 79.9 | 0.0% | 0% | 0.504 |

- 生成条件：`deepseek-flash`，temperature 0.75，max_tokens 420，时钟固定在白天，每格 3 条共 105 条，无一条报错。
- **composite** 是头号指标：风格保真 0.65 + 内容锚点 0.35（口径见 `docs/04-evaluation.md` 第 2.1 节）。fidelity 只量长度与句数分布，留作对照列——单看它会被「正确但空洞的助手腔」刷高。本表最直观的例子是爱音：fidelity 第一、composite 垫底（说得规范，但具体的事说得少）。两个数字背离时，去查锚点、具体回复和盲评；composite 也可能因为锚点封顶而失去区分力。
- **场景贴合分**衡量回复的长度与句数和「同角色同场景原作分布」的贴合程度，1.0 表示完全一致；本批均值 0.466（35 格）。它是**相对量**，只在同批次内做 before/after 对比，换模型、换夹具后跨批次不可比。
- 同格 3 条回复互不重样的比例 93/105；逐字照抄 prompt 里文本的比例 1%，而且抄的那 3 个字是口癖「诶……」，不是例句。
- 「说漏嘴」统计思考标签、内心独白、说话人回显、中文动作旁白四类，本批全为 0。
- 这张表的原始产物（`report/probe_*.jsonl` 与评分报告）按产物纪律不随库发布：重跑上面的命令，复现的是**流程**，拿到的是你自己的那批数。指标本来就是相对量、跨批次不可比，所以表里的数字无法从仓库逐字节复核，只当定性示例看。

同一批输入，来看看把四层 prompt 换成空 system 会怎样：

| 场景 | 空 system | 四层装配 |
|---|---|---|
| 乐奈 / 被安慰 | 「你的感受我完全能理解。当压力像潮水般涌来……」（380 字） | 「嗯。」「猫。屋檐下面。」（中位 10 字） |
| 乐奈 / 情绪低落 | 「当压力像潮水般涌来，连呼吸都觉得费力时……」（718 字） | 「嗯。……那边有猫。」 |

两列的出处不同：**四层那一列**来自上面的 `repo_standalone` 批次，可以自己复现；**空 system 那一列**是当时手工跑的一次对照（那两条通用助手腔回复的原样记录），探针产物没有随仓库发布，所以只能当定性示例。

> [!WARNING]
> 这一格样本量小，不构成证据，但能说明一件事：**探针必须自己装配 prompt**——仓库自带的夹具 system 是空的，不加 `--assemble`，测到的就是「没有任何角色 prompt 的裸模型」。

## 🧩 四层装配：prompt 是怎么拼的

量出来的东西落在四层里，顺序固定。稳定的放前面（方便命中缓存），每轮变化的放后面：

| 层 | 人话解释 | 内容 | 变化频率 | 乐奈找猫场景的字数 |
|---|---|---|---|---|
| `canon` | 这个人是谁 | 长档案 | 静态 | 12223 |
| `voice` | 这个人怎么说话 | 句式、口癖、对不同人的态度差异、「不准写模板腔」的硬约束 | 静态 | 1940 |
| `style_target` | 这一轮该说多少 | 字数、句数、句末、自称的具体数字；命中场景时换成该场景的数字 | 每轮 | 541 |
| `turn_logic` | 这一轮是什么场合 | 本轮的场景/话题指引 | 每轮（命中才注入） | 846 |

这四层就是本仓库对「特征怎么进 prompt」的完整回答。真实系统可以在前面接记忆、世界状态、日程，那些层与本方法无关。

装配结果可以用 `tools/gates/dump_prompt.py` 逐层打出来核对；改动前后都用 `--phase current`，保持输入、时钟和开关一致，并分别存到不同的报告目录。before/after 模式只用于开关消融。

**真实系统里，四层的前后还有什么？** 在完整的聊天系统里，模型每轮还需要知道「现在几点、角色在哪、刚才聊到哪、用户上周提过什么」。这套上下文按**工作区模式**组织：十几路候选材料先全部收集，打分排序、按预算裁剪，再按固定层序装配——四层就落在其中的 persona 位。仓库里蒸馏了这套骨架（`idiolect/workspace.py`，零依赖），详见 [`docs/08-context-workspace.md`](docs/08-context-workspace.md)：

```python
from idiolect.workspace import build_workspace_messages
messages = build_workspace_messages(
    "乐奈", "你今天又想去哪找猫",
    blocks=[("current_state", "乐奈在 RiNG 排练室，下午没课"),
            ("fact_workspace", "用户上周提过想养猫")],
    execution_packet="【本轮执行】回复 ≤19 字",   # 贴在本轮 user 末尾
)
```

## 📖 五个角色的 prompt 完整可查

这不是「给你一套方法，角色自己配」。**五名成员的四层 prompt 全部随仓库发布**：canon 长档案、语气 manifest、说话尺度、场景指引，一个字都不少，没有截断、没有省略，也不需要密钥或语料就能看。

```bash
# 装好包就能看（不需要克隆、不需要 key、不需要语料）
python -m idiolect prompt Rana "你今天又想去哪找猫"              # 这句话此刻的完整 system prompt
python -m idiolect prompt 乐奈 "你今天又想去哪找猫" --layers canon,voice   # 只看某一层

# 克隆后可以拿到分层审计版 + 发给模型的 messages 数组 + 各层字数
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"
py -X utf8 tools/gates/dump_prompt.py --all --matrix      # 5 角色 × 4 句话 = 20 份
```

产物三件：`prompt_<角色>_<phase>_<label>.txt`（人读的分层版）、`.json`（原样发给模型的 messages）、`.layers.json`（各层字数）。下面这张表就是 `--all --matrix` 里那个 comfort 格的实测值（输入「我一直在哭，快撑不住了」）：

| 角色 | canon | voice | style_target | turn_logic | 四层合计 |
|---|---|---|---|---|---|
| 爱音 | 16285 | 6656 | 533 | 539 | 24013 |
| 灯 | 8068 | 7008 | 530 | 616 | 16222 |
| 立希 | 12618 | 5579 | 533 | 491 | 19221 |
| 素世 | 9087 | 2279 | 532 | 479 | 12377 |
| 乐奈 | 12223 | 1940 | 531 | 509 | 15203 |

四层的正文在仓库里都能逐字读到：`canon` 与 `voice` 在 `idiolect/characters/*/`（canon.py / voice.py），说话尺度的数字来自 [`data/style_profiles.json`](data/style_profiles.json) 与 `idiolect/scene_length_targets.py` 的 130 个「角色 × 场景」格，场景指引来自 `idiolect/general_scenes.py` 与各角色包的 `turn_logic/scenes.py`。改 prompt 想看差在哪，用 `--phase current` 在改动前后分目录保存，再审阅 diff。

## 🛠️ 把整套工具跑一遍

上面「快速跑起来」用的是装好的包，这一节是仓库自带的工具链（需要先克隆仓库）：

```bash
py -X utf8 -m pip install -r requirements.txt
```

**看 prompt**（不需要密钥，也不需要语料）：

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix        # 五角色 × 四条会命中不同层的话
py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice
```

**一条命令体检**（不调 LLM、不写仓库文件，适合当提交前检查）：

```bash
py -X utf8 tools/offline_smoke.py          # 装配 + 场景覆盖 + 触发矩阵 + 内容红线 + 数据形状 + 门禁 + 单测 + 零写校验
py -X utf8 tools/offline_smoke.py --fast   # 跳过门禁与单测，一秒出结果
```

**跑探针**（需要 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）：

```bash
py -X utf8 tools/probe/make_fixtures.py                                # 生成占位夹具
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
py -X utf8 tools/probe/oob_probe.py --label oob1 --runs 2 --gate       # 越界拒答探针（高危破功即 FAIL）
py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate           # 多轮风格漂移探针
```

**评测时钟**：角色对时段敏感（凌晨和下午的回答不一样），所以评测统一用固定在白天的假时钟（`tools/mock_clock.py`），不让「现在几点」变成隐藏变量。下面这条命令只是**打印**要设的环境变量（子进程改不了父进程的 shell），贴进 shell 才生效：

```bash
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00
```

**用自己的语料重算全部数字**（语料要自己抓，见 [`docs/02-corpus.md`](docs/02-corpus.md)）：

```bash
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_scene_targets.py     # 重建 idiolect/scene_length_targets.py 的 130 个目标
py -X utf8 tools/distill/export_profiles.py          # 评分用的画像
py -X utf8 tools/distill/export_profiles.py --check  # 校验已发布画像与语料是否一致
```

没有语料也能跑探针：评分用的画像随仓库发布（`data/style_profiles.json`），启动日志会打印画像来源。

## 🎭 换成别的角色：skill 串起全流程

上面那些数字属于这五个人。**方法本身不绑作品**——要拿它跑自己的角色，仓库里带了五个 skill，把「找语料 → 蒸馏 → 建角色包 → 评测」串成一条流水线（Claude Code 或兼容 skill 的 agent 会自己加载；人也可以当操作手册读）：

| skill | 干什么 | 产物 |
|---|---|---|
| [`.claude/skills/idiolect-corpus`](.claude/skills/idiolect-corpus/SKILL.md) | 把你自己的台词集整理成规定的语料格式与切分；决定角色 key 并列出**所有**要跟着改的表 | `raw/gold/{lang}.jsonl` + `gold_stats.json` |
| [`.claude/skills/idiolect-distill`](.claude/skills/idiolect-distill/SKILL.md) | 从语料算出五类特征的派生统计 | `data/` 六个 JSON + `idiolect/scene_length_targets.py` |
| [`.claude/skills/idiolect-cast`](.claude/skills/idiolect-cast/SKILL.md) | 建角色包（canon / voice / turn_logic / voice_check）并注册进四层 | `idiolect/characters/<key>/` |
| [`.claude/skills/idiolect-evaluate`](.claude/skills/idiolect-evaluate/SKILL.md) | 跑探针与四件套评分，留 before/after 证据 | `report/probe_*.jsonl` + 报告 |
| [`.claude/skills/idiolect-pipeline`](.claude/skills/idiolect-pipeline/SKILL.md) | 编排上面四个：交接物、每步的门禁、哪些必须人写 | 一条可复现的完整链路 |

一句话区分：**能从语料算出来的都是自动的**（场景体系、长度目标、风格画像、口癖、词表），**canon 长档案、语气 manifest 和场景正文必须你自己写**——语料是活动剧情的快照，日常道具天然缺席，光靠统计写不出「这个人是谁」。`idiolect-pipeline` 里有一张自动/人写的对照表。

## ⚠️ 关于边界与提醒

> [!CAUTION]
> **不分发原作文本。** 仓库里只有聚合数字：字数分布、句数、标点出现率、口癖频次、场景基线（130 个「角色 × 场景」组合）、评分画像。发布前已剥掉基线文件里的例句字段，体检脚本和单测各有一道检查盯着这条线。角色与作品的权利归 Bushiroad / Craft Egg 及相关权利方，本项目与权利方无关，见 [`NOTICE.md`](NOTICE.md)。

> [!NOTE]
> **分数是相对量。** 贴合分、fidelity、composite 都只用于同批次内的 before/after 比较，换模型、换夹具、换时钟之后跨批次不可比。

**已知尚未解决的问题：**

- 零样本用词的代价：禁用可整句照抄的例句之后，长度贴合度从 0.512 掉到 0.461（两个数来自旧批次，产物未随仓库发布）。这个代价是自愿接受的。
- 立希的起手句式被过度矫正：原作 39% 的回合以名词直出，本批探针里升到 62%（`tools/score/_noun_initial.py <批次名>` 会连原作基线一起打出），方向反了。
- 灯的停顿记账：参照系剔除了沉默回合，但她的十二点省略号是内容不是赘余，两头不讨好。
- 探针夹具的可测性：「你刚才那句什么意思」需要上文有一句可指代的话，占位夹具没有上文，这类场景的分不可读。
- 立希与灯的场景贴合分仍是五个人里最低的两个（0.386 / 0.365）。

**语料是快照。** 官方会持续上新剧情，重抓得到的分布会和原批次不同。所有派生统计都标了生成脚本，可以重算。

## 📚 文档

不确定从哪篇读起，先翻 [`docs/README.md`](docs/README.md)：它按「你想做什么」分三条路，另有一张名词表（回合 / 场景 / 四层 / 探针 / 夹具 / 臂 / 门禁…）。

| 文档 | 内容 |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | 方法总纲：闭环、四条不变量、证据分级、已知残余 |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | 安装与五分钟上手 |
| [`docs/02-corpus.md`](docs/02-corpus.md) | 语料获取、清洗、派生统计清单 |
| [`docs/03-features.md`](docs/03-features.md) | 五类特征怎么算、怎么落地、触发词纪律 |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | 三件套指标、池化、门禁、越界拒答与多轮漂移、证据一致性、夹具设计、常见误读 |
| [`docs/05-tooling.md`](docs/05-tooling.md) | 工具手册（含 prompt dump、mock 时钟、offline smoke） |
| [`docs/06-lessons.md`](docs/06-lessons.md) | 踩坑清单：每条约束是被什么教出来的 |
| [`docs/07-turn-logic-and-postprocessing.md`](docs/07-turn-logic-and-postprocessing.md) | turn_logic 模块与 voice_check 后处理的搭建流程、接线与验收 |
| [`docs/08-context-workspace.md`](docs/08-context-workspace.md) | 上下文工作区：四层在真实聊天系统里的前后文 |

## ⚖️ 版权、许可与免责

### 代码：MIT

`idiolect/`、`tools/`、`docs/`、`tests/`、`conftest.py`、`pyproject.toml` 以 **MIT** 发布，见 [`LICENSE`](LICENSE)（`Copyright (c) 2026 puresky`）。商用、改写、再发布都可以，保留版权声明即可。

### 角色与作品：不属于本仓库

《BanG Dream! It's MyGO!!!!!》的角色名、角色设定、世界观、剧情与音乐的权利归 **Bushiroad / Craft Egg 及相关权利方**。本仓库是一个**非官方同人技术项目**：

- 与权利方**没有任何关联**，未获得授权、赞助或背书；
- 角色长档案（`idiolect/characters/*/canon.py`）由本仓库作者**根据公开资料整理**，用于技术研究，不是官方设定；
- 示例插画（[`assets/readme/hero.png`](assets/readme/hero.png)）**不是官方素材**，属于同人性质的使用；角色权利仍归权利方，若权利方提出要求会立即移除。

### 仓库里有什么、没有什么

| 有 | 没有 |
|---|---|
| 装配与后处理代码；抓取 / 蒸馏 / 评分脚本；`data/` 下六个**聚合统计**文件（字数分位、句数、标点出现率、口癖频次、场景基线、评分画像）；九篇方法论文档 | 原作剧本、台词、歌词、音频、游戏素材；任何微调后的模型权重；任何原句级语料 |

`data/` 里最长的字符串是 56 字的说明字段；`scene_char_baseline.json` 与 `scene_stats.json` 的例句字段在发布前已被 `--no-exemplars` 剥掉。两道检查盯着这条线：`tests/test_tooling_contracts.py::test_shipped_profiles_have_no_text` 与 `offline_smoke.py` 的「数据.无原作文本」项。

### 你要自己抓语料的话

`tools/corpus/` 只是抓取与清洗工具，**不含数据**。使用者需自行确认来源站点的服务条款与所在地区的法律，并自行承担相应责任。本仓库不附带 HuggingFace 数据集（`KomeijiForce/BanG_Dream_Events`）的副本，只保留把它整理成统一形态的脚本。

完整声明见 [`NOTICE.md`](NOTICE.md)。
