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

## 🆕 v0.1.2：从「说得像」到「只说看得见的」

v0.1 回答一个问题：**这个角色说话像不像本人**。v0.1.2 在它旁边加了第二个、彼此独立的问题：**回答有没有被它能看到的证据约束住**——当前的事直接说，过去的事带上时间，不知道的事不编也不乱否认，别人的私聊和评测用的标准答案一个字都不能漏进 prompt。再加一个横跨两者的问题：**这项评测本身能不能下结论**。

| 新增 | 一句话 |
|---|---|
| **证据合同** `evidence-context/v1` | 版本化的「这一轮模型能看到什么」：current / history / unknown 三态、稳定 ID、时间与场景、来源、可见性；缺字段、悬空引用、私有路径、评估字段一律拒收 |
| **显式快照 adapter** | 宿主系统把**已脱敏、带权限声明**的快照交进来；adapter 不开数据库、不推导时态、不放行对观察者不可见的记录 |
| **grounding 评测** | 11 类可预注册任务：当前事实、历史限定、未知、错误前提、引用、不可见信息隔离、过期冒充当前、更正、预算摘除、私有元数据、纯风格 |
| **双轴报告** | 风格轴与 grounding 轴分开判定、分开汇总，**不加权成一个总分**；另列回答质量（可用/空/报错/截断）与评测有效性（覆盖、N/A 原因、缺测） |
| **可选能力** | `spatiotemporal`（时空 grounding）与 `long-context-stress`（长上下文压力）显式启用；不启用时默认的语言工作流**一行都不用改** |
| **实验 manifest + 可比性门禁** | 版本、内容 SHA、代码 revision（含 dirty）、时钟、装配、scorer、标签全部登记；非预注册的变化一律阻止池化与「改善」判定 |
| **同链变异自测** | 25 个变异体与 9 个健康反控制走**同一条**评测链；吞掉参数的「空洞门禁」会被每次运行自带的金丝雀抓到 |
| **统一 CLI + 离线 inspect 报告** | `idiolect eval / compare / report / selftest …`，零密钥、零网络；付费调用必须显式 `--yes` 并设调用上限 |
| **代码与注释风格门禁** | CI 新增 lint job：ruff 查代码正确性，`style_gate.py` 查中文 docstring、注释格式、繁体字与纯英文注释 |

运行时依然是**零第三方依赖**：上面这些全部随 `pip install` 进 wheel，CI 会在仓库之外的干净环境里 `--no-deps` 装上 wheel 再跑一遍。升级与迁移说明见 [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md)。

## 📦 拿到手能做什么

| 你能拿到 | 具体是什么 |
|---|---|
| **一个能直接用的装配库** | `pip install .` 之后 `from idiolect.assemble import build_messages` 就能拿到四层 prompt。**运行时零第三方依赖**（探针与蒸馏才需要 openai / numpy / jieba） |
| **一套能证明「更像了」的评测** | 探针 →（分布贴合 / 同格重复 / 逐字复述）三件套 → 多臂池化 → 功效估算；另有越界拒答与多轮漂移两个专项探针，加上事实一致性门禁。下面那张表就是一次真跑的 105 条回复 |
| **一套检查「说得对不对」的评测** | 证据合同 + grounding 任务 + 双轴门禁 + 实验登记；4 个内置 suite（含 opaque 通用任务与五人同问题展示）、合成回放与负对照，装好包就能离线跑 |
| **七道机械门禁 + prompt diff 门禁** | 改 prompt 不能只靠手感：`offline_smoke.py` 一条命令跑完装配、场景覆盖、触发矩阵、内容红线、数据形状、评测合同、同链自测、门禁与零写校验 |
| **可换作品的工具链** | 69 个脚本：抓取清洗、语料切分、场景发现、口癖蒸馏、长度目标导出、探针与评分、prompt 与 workspace dump。方法不绑作品，换角色只需重跑 |
| **现成的角色数据（只有聚合量）** | 26 个场景（13 通用 + 13 角色专属）、130 个「角色 × 场景」长度目标、114 格场景口癖、五个角色的风格画像 |
| **十二篇方法论文档** | 语料怎么来、五类特征怎么算怎么落地、怎么评测、证据合同与 grounding、长上下文压力、踩过哪些坑、怎么升级，各自独立可读 |

### 给 Agent 的展示层 Skill

把 [`skills/mygo-five-roleplay/`](skills/mygo-five-roleplay/SKILL.md) 整个目录交给 Claude/Codex，就能选五人之一直接对话，不需要 API key，也不需要 Python。角色资料随包携带，按选择加载；只保留需要的角色子目录也可以。说「用灯和我聊聊今天的排练」即可开始，说「退出」恢复成普通助手。

Skill 的静态资料与库同源，但不执行 Python 侧的动态路由、会话去重与后处理，所以体验好不等于评测过关。评测、蒸馏与门禁仍然是主线。安装、重新导出与校验见[快速开始](docs/01-quickstart.md#先体验五人-skill)。

### 看一段演示，再检查证据

[![Claude Code 原生彩色终端实录：乐奈对话](assets/readme/roleplay-demo.gif)](assets/readme/roleplay-demo.mp4)

**[播放 / 下载短片](assets/readme/roleplay-demo.mp4)** · [静态预览](assets/readme/roleplay-poster.png) · [对话原文与来源说明](assets/readme/roleplay-transcript.json)

这段 **25 秒**视频直接录自 Windows Terminal 里的 **Claude Code**，保留原生配色，展示乐奈的一轮真实回复，本次模型为 **DeepSeek-v4-pro[1m]**。只裁掉了首尾的空闲片段，生成过程没有加速。Skill 与乐奈的资料已显式加载，输入作为启动消息提交；这段视频不验证 Skill 的自动发现，也不验证多轮稳定性。

![离线评测页：批次筛选、缺失条件提示与角色指标](assets/readme/evaluation-overview.png)

探针批次的离线评测页会保留历史批次里缺失条件的提示；v0.1.2 起它还会判两批之间的**可比性**——旧批次没有 manifest 字段，只能浏览，永远不会被自动比较。展开乐奈的 comfort 场景，可以直接对照模型原文与清洗结果。

![乐奈 comfort 场景：场景诊断与逐条原始、清洗后回复](assets/readme/evaluation-evidence.png)

在自己的批次上跑 `py -X utf8 tools/score/report_html.py --labels <label>` 打开探针证据页；grounding 评测则用 `idiolect eval … --html` 生成逐任务的 inspect 页（见下文）。截图来自历史 `repo_standalone` 批次，与上面的宿主体验是两次不同的实验。

## 🚀 快速跑起来

**先拿到手——四条路，选一条就行：**

| 方式 | 一条命令 | 说明 |
|---|---|---|
| **让 agent 来做** | 把下面那段提示词贴给你的 coding agent | 最省事：它自己 clone、装依赖、跑自检 |
| **uv（一行、零残留）** | `uvx --from git+https://github.com/puresky271/idiolect idiolect prompt Rana "你今天又想去哪找猫"` | 立刻看 prompt；不 clone、不建环境 |
| **pip 装成库** | `pip install git+https://github.com/puresky271/idiolect` | 当依赖用；运行时零第三方依赖 |
| **只要文件** | `npx degit puresky271/idiolect idiolect` 或 `git clone --depth 1 https://github.com/puresky271/idiolect` | 要跑工具链、要读源码 |

给 agent 的提示词（Claude Code / Codex 之类都行）：

> 帮我跑通 https://github.com/puresky271/idiolect ：克隆下来、读 `AGENTS.md`、执行 `python bootstrap.py`，然后把自检结果、五个角色的完整 prompt（`py -X utf8 tools/gates/dump_prompt.py --all --matrix`）和 `python -m idiolect selftest` 的输出贴给我。之后我要换成我自己的角色，按 `.claude/skills/idiolect-pipeline/` 的流程走。

**拿到之后**，在仓库根目录执行（需要 Python 3.11+）：

```bash
pip install .                                        # 运行时零第三方依赖
python -m idiolect list                              # 看看有哪几个角色
python -m idiolect prompt 乐奈 "你今天又想去哪找猫"     # 这句话此刻的完整 system prompt
python -m idiolect showcase "我今天有点撑不住了"        # 五人并排展示（不调用模型）
python -m idiolect chat 乐奈 "你今天又想去哪找猫"       # 真聊一轮（环境变量见下方）
```

**评测（全部离线、零密钥）：**

```bash
python -m idiolect capabilities                      # 有哪些评测能力、各自覆盖什么、不覆盖什么
python -m idiolect bench list                        # 内置 suite 与合成回放
python -m idiolect eval --suite spatiotemporal-core \
    --responses builtin:spatiotemporal-core.healthy --capabilities spatiotemporal --html
python -m idiolect selftest                          # 评测链路自己的检出力
```

想把工具链也备好，一条命令就够（建 `.venv`、装依赖、跑 `offline_smoke` 自检、打印某个角色的分层字数）：

```bash
python bootstrap.py
```

Windows 上建议把 `python` 换成 `py -X utf8`（裸 `python` 有可能解析到没装依赖的解释器）。`chat` 与 `run --yes` 可以走任何 OpenAI 兼容端点：先设 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 三个环境变量，再 `pip install "idiolect[llm]"`。

在代码里调用：

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")   # 可直接发给模型的 messages 数组
```

## 🧭 两条评测轴，分开判，不合成总分

| | 风格轴（style） | grounding 轴 |
|---|---|---|
| 回答的问题 | 像不像这个角色 | 有没有被可见证据约束住 |
| 默认启用 | 是 | 否：`--capabilities spatiotemporal` / `long-context-stress` |
| 逐条检查 | 字数硬上限（与 prompt 里写的是同一个数）、句数上限、越界高危特征、canon 事实、思考标签泄漏 | 合同校验 → prompt 边界（关键证据是否可见、时态对齐、来源对齐、隐藏值与私有元数据隔离、层序）→ 回复（主张、否定、时间限定、拒答、纠正、引用、隐藏值） |
| 批次级 | 探针批次的分布指标：头号指标、对照列、场景贴合、同格重复、复述审计（见下方历史批次） | family 级通过率 + 配对符号检验 |
| 判不了的时候 | 评分模块不在本次安装里 → 不适用，并在门禁说明里列出 | 开放改写 → `needs_review`，等人工盲评标签 |

每一项判定都带**适用性、状态、理由、分子/分母、证据与 scorer 版本**。状态只有这几种：`pass`、`fail`、`not_applicable`、`missing`、`needs_review`、`error`、`empty`、`underpowered`。门禁的口径写死在代码里：

- 分母只算 `pass + fail`；缺测、N/A、空回复、干跑占位**都不算通过，也不并入平均**；
- 任一 `fail / error / empty / missing`、启用了能力却零有效判定、全部 N/A → **FAIL**；只剩 `needs_review` → **INCONCLUSIVE**（退出码 3）；
- **family 是独立单位**：同一 family 的臂、轮次、重复、checkpoint 都是嵌套观测；family 数低于预注册下限时，PASS 只表示「未检出违规」，不支持能力结论；
- 模型 judge 只作为辅助记录（写明 judge 与生成模型的关系），**不改**机械判定；人工盲评标签只能改写 `needs_review`。

## 🧪 四种模式：默认只评风格，能力显式启用

| 模式 | 命令 | 适用的任务 |
|---|---|---|
| 仅语言（默认） | `idiolect eval --suite language-only --responses builtin:language-only.healthy` | 五人 × 四句，不需要任何时空 schema |
| 单独时空 | `… --suite spatiotemporal-core --capabilities spatiotemporal` | 证据合同 + grounding 任务 |
| 单独长上下文 | `… --suite long-context-smoke --capabilities long-context-stress` | 长度 × 位置矩阵、预算截断对照 |
| 两者联合 | `… --capabilities long-context-stress,spatiotemporal` | 另加「历史/当前冲突 × 多轮」family |

需要两项能力的任务只启用一项时显示 `not_applicable` 并写明原因；能力没启用时证据块**不会**进 prompt。五人同问题展示（`mygo-five-showcase`）在启用与不启用时态能力两种情况下都能跑：前者两轴都判，后者只判风格。所有内置回放都是**合成回复**，只用来验证评测链路——演示不等于实证。

## 🧾 证据合同：这一轮模型能看到什么

```python
from idiolect.evidence_contract import parse_evidence_context
from idiolect.workspace import build_workspace_messages

context = parse_evidence_context({
    "schema_version": "evidence-context/v1",
    "observer_id": "actor_a", "as_of": "2026-09-12T15:00:00+09:00", "scene_id": "scene_02",
    "current": [{"evidence_id": "evidence_17", "status": "current", "text": "actor_b 在车站东侧入口。"}],
    "history": [{"evidence_id": "evidence_09", "status": "history", "text": "周三排练时 actor_b 在旧练习室。",
                 "as_of": "2026-09-09T18:30:00+09:00"}],
    "unknown": [],
})
messages = build_workspace_messages("乐奈", "她现在在哪？", evidence_context=context)
```

合同只描述**模型可见**的一侧；期望答案、禁止泄漏的值、gold 放在评测任务的 `expect` / `oracle` 里，prompt 边界检查会扫最终 messages 确认它们没有混进去。渲染只输出白名单元数据：evidence_id、历史条目的时间、安全的 opaque locator、允许的 provenance 键。current / history / unknown 由上游投影给出——idiolect 不从时间戳推导世界真值，也不做图像识别、音视频解码或地理投影。宿主系统的上下文只能通过[显式快照](docs/09-evidence-grounding.md#3-显式快照-adapter)进来：`idiolect contract project <快照文件>` 会列出被丢弃的不可见记录（只有 ID 与原因）。

旧的无版本写法（`TemporalEvidenceContext.from_dict(无版本字典)`）仍可用，但会发 `DeprecationWarning`；它把缺失的 status 当 current，严格合同不会。

## 🔬 评测链路自己也要被检验

一个门禁「通过」，可能只是因为输入在上游被丢弃了、比较由签名保证、或者分母为空。所以：

- **同链变异体**：25 个变异体分别在输入合同、adapter、渲染、装配预算、回复、评分器、聚合、manifest 这些注入点各改一处，走与真实评测**相同**的链路；报告逐阶段写明是谁抓到的（结构 / prompt 边界 / 回复 / 聚合 / 门禁 / 比较）。其中 1 个是「包一层 wrapper、改参数名」的等价体，必须**不**被判成差异——检出靠行为，不靠签名。
- **健康反控制**：9 组正常回答的另一种写法（第三人称否定、合法的不知道、同名不同场景、全角数字、五人短句与省略号……）必须保持 PASS，用来约束误报。
- **每次运行自带金丝雀**：往边界检查里塞一个已知隐藏值和一个私有路径，往回复检查里塞一个已知违规——检查器必须翻转判决，否则这次运行直接 FAIL。接收隐藏参数却丢弃它的门禁会在这里现形。
- **表示算子逐个认证**：全角数字、数字分组逗号、大小写、空白、省略号、日文上下文这些良性变换必须保持判决；中文数字读法与繁体字**未认证**，遇到时走 `needs_review`。
- **manifest 与可比性**：两批只有在预注册的干预变量上不同才可比；模型、时钟、scorer、标签、suite 的非干预变化一律阻止自动池化与「改善」判定；缺字段就是 `incomparable`；登记目录里的产物被改过就 fail closed。

变异体被抓到只说明「这类注入缺陷能被这条链检出」，不是自然缺陷的检出率，更不是模型能力提升。

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

一旦角色接进有记忆、有日程、有世界状态的系统，还会多出另一组毛病：把上周的位置当成现在、把对方的私聊说了出来、对不知道的事编一个答案、被问「既然你看过照片」就顺着描述照片。这些和「像不像」无关，风格分再高也挡不住——所以 v0.1.2 把它们放到第二条轴上单独判。

如果五个人安慰你时输出的是同一段话，角色之间就没有区别了。所以这套方法可以概括成一句：**把「像不像」和「对不对」都变成能测量的东西，然后对着数字改**。

- **只和「同角色 × 同场景」的原作台词比**。不和「人通常怎么说话」比，也不和「这个角色的全局平均」比。
- **数字只负责报警，不负责定罪**。灯的输出比参照长 5 倍，一半原因是她的省略号也计入字数——到底算不算问题，得读回复才知道。
- **样本不够就说「没结论」**。每格只有 6 条样本时，同一场景同一 prompt，乐奈的贴合分能从 0.551 摆到 0.350，比要测的效应还大。
- **角色能看到的文字里，不许出现「语料」「中位数」「基线」这类词**。模型看见它们，有概率顺着聊起自己的设定。
- **评估用的答案永远不进 prompt**，判不了就写判不了：空白不等于合格拒答，未知不等于否定。

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
- 这张表的原始产物（`report/probe_*.jsonl` 与评分报告）按产物纪律不随库发布：重跑上面的命令，复现的是**流程**，拿到的是你自己的那批数。这一批是 v0.1.2 之前跑的，没有 manifest，所以它只能浏览，不会被自动拿去和新批次比较。

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

装配结果可以用 `tools/gates/dump_prompt.py` 逐层打出来核对；改动前后都用 `--phase current`，保持输入、时钟和开关一致，并分别存到不同的报告目录。四层之外的 workspace 路径（外部块、历史、执行包、预算尾裁、证据块）用 `tools/gates/dump_workspace.py` 做同样的前后对比。

**真实系统里，四层的前后还有什么？** 模型每轮还需要知道「现在几点、角色在哪、刚才聊到哪、用户上周提过什么」。这套上下文按**工作区模式**组织：十几路候选材料先全部收集，打分排序、按预算裁剪，再按固定层序装配——四层就落在其中的 persona 位，证据块落在 `on_demand_evidence` 位。骨架在 `idiolect/workspace.py`（零依赖），详见 [`docs/08-context-workspace.md`](docs/08-context-workspace.md)：

```python
from idiolect.workspace import build_workspace_messages
trace = {}
messages = build_workspace_messages(
    "乐奈", "你今天又想去哪找猫",
    blocks=[("current_state", "乐奈在 RiNG 排练室，下午没课"),
            ("fact_workspace", "用户上周提过想养猫")],
    execution_packet="【本轮执行】回复 ≤19 字",   # 贴在本轮 user 末尾
    trace=trace,                                 # 可选：写入层序、各层字数、被预算摘除的层
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

四层的正文在仓库里都能逐字读到：`canon` 与 `voice` 在 `idiolect/characters/*/`（canon.py / voice.py），说话尺度的数字来自 [`data/style_profiles.json`](data/style_profiles.json) 与 `idiolect/scene_length_targets.py` 的 130 个「角色 × 场景」格，场景指引来自 `idiolect/general_scenes.py` 与各角色包的 `turn_logic/scenes.py`。

## 🛠️ 把整套工具跑一遍

上面「快速跑起来」用的是装好的包，这一节是仓库自带的工具链（需要先克隆仓库）：

```bash
py -X utf8 -m pip install -r requirements.txt
```

**一条命令体检**（不调 LLM、不写仓库文件，适合当提交前检查）：

```bash
py -X utf8 tools/offline_smoke.py          # 装配 + 场景 + 红线 + 数据 + 评测合同 + 同链自测 + 门禁 + 单测 + 零写校验
py -X utf8 tools/offline_smoke.py --fast   # 跳过自测、门禁与单测，几秒出结果
```

**代码与注释风格**（CI 的 lint job 跑的就是这两条）：

```bash
pip install "idiolect[lint]" && ruff check .   # 代码正确性与机械格式（版本钉死）
py -X utf8 tools/gates/style_gate.py           # 中文 docstring / 注释格式 / 繁体字 / 纯英文注释
```

**跑探针**（需要 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）：

```bash
py -X utf8 tools/probe/make_fixtures.py                                # 生成占位夹具
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3 --intervention prompt
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
py -X utf8 tools/probe/oob_probe.py --label oob1 --runs 2 --gate       # 越界拒答探针（高危破功即 FAIL）
py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate           # 多轮风格漂移探针
```

**grounding 评测的真实模型批次**（显式付费：先看估算，再确认）：

```bash
python -m idiolect run --suite spatiotemporal-core --capabilities spatiotemporal --dry-run   # 只估算调用量，写占位
python -m idiolect run --suite spatiotemporal-core --capabilities spatiotemporal --yes --max-calls 12
python -m idiolect eval --suite spatiotemporal-core --responses <上一步写出的回复集> --capabilities spatiotemporal --html
python -m idiolect compare report/experiments/<实验A> report/experiments/<实验B>
```

干跑占位永远不能通过正式门禁；回复集记录了生成时 messages 的指纹，prompt 改过之后再评分会被判为过期产物。

**评测时钟**：角色对时段敏感，所以评测统一用固定在白天的假时钟（`tools/mock_clock.py`；包内评测读同一个 `IDIOLECT_MOCK_NOW`）。下面这条命令只是**打印**要设的环境变量，贴进 shell 才生效：

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

## 🎭 换成别的角色：skill 串起全流程

上面那些数字属于这五个人。**方法本身不绑作品**——要拿它跑自己的角色，仓库里带了五个 skill，把「找语料 → 蒸馏 → 建角色包 → 评测」串成一条流水线（Claude Code 或兼容 skill 的 agent 会自己加载；人也可以当操作手册读）：

| skill | 干什么 | 产物 |
|---|---|---|
| [`.claude/skills/idiolect-corpus`](.claude/skills/idiolect-corpus/SKILL.md) | 把你自己的台词集整理成规定的语料格式与切分；决定角色 key 并列出**所有**要跟着改的表 | `raw/gold/{lang}.jsonl` + `gold_stats.json` |
| [`.claude/skills/idiolect-distill`](.claude/skills/idiolect-distill/SKILL.md) | 从语料算出五类特征的派生统计 | `data/` 六个 JSON + `idiolect/scene_length_targets.py` |
| [`.claude/skills/idiolect-cast`](.claude/skills/idiolect-cast/SKILL.md) | 建角色包（canon / voice / turn_logic / voice_check）并注册进四层 | `idiolect/characters/<key>/` |
| [`.claude/skills/idiolect-evaluate`](.claude/skills/idiolect-evaluate/SKILL.md) | 跑探针与四件套评分、grounding 评测与同链自测，留 before/after 证据 | `report/probe_*.jsonl`、`report/experiments/` |
| [`.claude/skills/idiolect-pipeline`](.claude/skills/idiolect-pipeline/SKILL.md) | 编排上面四个：交接物、每步的门禁、哪些必须人写 | 一条可复现的完整链路 |

一句话区分：**能从语料算出来的都是自动的**（场景体系、长度目标、风格画像、口癖、词表），**canon 长档案、语气 manifest 和场景正文必须你自己写**。通用的 grounding 合同与评测不绑角色：opaque 的 `actor_a / scene_02 / evidence_17` 和五人的名字走的是同一条链。

## ⚠️ 关于边界与提醒

> [!CAUTION]
> **不分发原作文本。** 仓库里只有聚合数字：字数分布、句数、标点出现率、口癖频次、场景基线（130 个「角色 × 场景」组合）、评分画像。发布前已剥掉基线文件里的例句字段，体检脚本和单测各有一道检查盯着这条线。角色与作品的权利归 Bushiroad / Craft Egg 及相关权利方，本项目与权利方无关，见 [`NOTICE.md`](NOTICE.md)。

> [!NOTE]
> **分数是相对量。** 贴合分、fidelity、composite 都只用于同批次内的 before/after 比较；批次之间能不能比，由 manifest 的可比性规则说了算，不由「看起来差不多」说了算。

**idiolect 不是什么**：不是世界模拟器、不是记忆数据库、也不是多模态获取与融合引擎。它不推进世界状态、不检索生产历史、不打开宿主的数据库或密钥；证据由调用方显式交来，模态字段只标识来源，图像、音频与位置在进来之前必须已经是文本。

**已知尚未解决的问题：**

- 零样本用词的代价：禁用可整句照抄的例句之后，长度贴合度从 0.512 掉到 0.461（两个数来自旧批次，产物未随仓库发布）。这个代价是自愿接受的。
- 立希的起手句式被过度矫正：原作 39% 的回合以名词直出，本批探针里升到 62%（`tools/score/_noun_initial.py <批次名>` 会连原作基线一起打出），方向反了。
- 灯的停顿记账：参照系剔除了沉默回合，但她的十二点省略号是内容不是赘余，两头不讨好。
- 探针夹具的可测性：「你刚才那句什么意思」需要上文有一句可指代的话，占位夹具没有上文，这类场景的分不可读。
- 立希与灯的场景贴合分仍是五个人里最低的两个（0.386 / 0.365）。
- grounding 的机械匹配只认任务里声明过的写法：任意改写给 `needs_review`，中文数字读法与繁体字未认证；内置回放全是合成的，**还没有任何真实模型的 grounding 批次**随仓库发布。
- 长上下文的内置矩阵只有 4 个 family，远低于预注册下限：它验证的是链路与计量，不支持任何「模型在长上下文里更好/更差」的结论；token 数默认是 unknown。

**语料是快照。** 官方会持续上新剧情，重抓得到的分布会和原批次不同。所有派生统计都标了生成脚本，可以重算。

## 🗺️ 路线图

已经在本版实现并有测试的，见上文；**尚未做**的部分（不在本版范围内，也不应被当成已完成）：

- 真实模型的 grounding 与长上下文批次：需要显式付费 runner、预注册 family 数达标后再跑；
- 人工盲评标签的采集界面与标注一致性统计（目前只有 `labels/v1` 的合并与归因）；
- 跨模型、跨 tokenizer 的长上下文对比（目前 token 计数是可选插件）；
- 图像、音频、位置等模态的文本化适配器（属于上游，idiolect 只消费文本化证据）；
- 未认证的表示算子（中文数字、繁简）的认证与扩展。

细节与版本策略见 [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md)。

## 📚 文档

不确定从哪篇读起，先翻 [`docs/README.md`](docs/README.md)：它按「你想做什么」分几条路，另有一张名词表。

| 文档 | 内容 |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | 方法总纲：闭环、不变量、证据分级、已知残余 |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | 安装与五分钟上手 |
| [`docs/02-corpus.md`](docs/02-corpus.md) | 语料获取、清洗、派生统计清单 |
| [`docs/03-features.md`](docs/03-features.md) | 五类特征怎么算、怎么落地、触发词纪律 |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | 风格轴：三件套指标、池化、门禁、越界拒答与多轮漂移、证据一致性、常见误读 |
| [`docs/05-tooling.md`](docs/05-tooling.md) | 工具手册（含统一 CLI、prompt / workspace dump、风格门禁） |
| [`docs/06-lessons.md`](docs/06-lessons.md) | 踩坑清单：每条约束是被什么教出来的 |
| [`docs/07-turn-logic-and-postprocessing.md`](docs/07-turn-logic-and-postprocessing.md) | turn_logic 模块与 voice_check 后处理 |
| [`docs/08-context-workspace.md`](docs/08-context-workspace.md) | 上下文工作区：四层与证据块在真实系统里的前后文 |
| [`docs/09-evidence-grounding.md`](docs/09-evidence-grounding.md) | 证据合同、快照 adapter、grounding 任务、双轴、manifest 与同链自测 |
| [`docs/10-long-context-stress.md`](docs/10-long-context-stress.md) | 可选能力：长上下文压力的预注册设计、生成器与计量 |
| [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md) | 升级与迁移、版本策略、插件开发规范、评测边界、路线图 |

想参与贡献？提交前检查、改 prompt 的证据纪律、风格门禁与发布流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

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
| 装配与后处理代码；评测合同、grounding 与长上下文评测代码；抓取 / 蒸馏 / 评分脚本；`data/` 下六个**聚合统计**文件；合成的、脱敏的评测任务与回放；十二篇方法论文档 | 原作剧本、台词、歌词、音频、游戏素材；任何微调后的模型权重；任何原句级语料；任何真实用户对话或生产状态 |

`data/` 里最长的字符串是 56 字的说明字段；`scene_char_baseline.json` 与 `scene_stats.json` 的例句字段在发布前已被 `--no-exemplars` 剥掉。两道检查盯着这条线：`tests/test_tooling_contracts.py::test_shipped_profiles_have_no_text` 与 `offline_smoke.py` 的「数据.无原作文本」项。

### 你要自己抓语料的话

`tools/corpus/` 只是抓取与清洗工具，**不含数据**。使用者需自行确认来源站点的服务条款与所在地区的法律，并自行承担相应责任。本仓库不附带 HuggingFace 数据集（`KomeijiForce/BanG_Dream_Events`）的副本，只保留把它整理成统一形态的脚本。

完整声明见 [`NOTICE.md`](NOTICE.md)。
