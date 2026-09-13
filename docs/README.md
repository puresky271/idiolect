# 文档索引

九篇文档，按「你在做什么」分三条路。每篇都能单独读，但编号就是推荐顺序。

## 按目的挑路

| 你想做的事 | 读这几篇 |
|---|---|
| **只想让角色说得像**（把装配库接进自己的系统） | [`01-quickstart.md`](01-quickstart.md) → [`03-features.md`](03-features.md) 第 1 节 → [`08-context-workspace.md`](08-context-workspace.md) 第 3 节 |
| **要改 prompt / 加场景模块 / 加角色** | [`05-tooling.md`](05-tooling.md) → [`03-features.md`](03-features.md) → [`07-turn-logic-and-postprocessing.md`](07-turn-logic-and-postprocessing.md) → 改完过 [`04-evaluation.md`](04-evaluation.md) 的门禁 |
| **要重算语料 / 换一部作品** | [`02-corpus.md`](02-corpus.md) → [`03-features.md`](03-features.md) → [`04-evaluation.md`](04-evaluation.md) |
| **被某个坑卡住了** | [`06-lessons.md`](06-lessons.md)（按主题分组，症状 → 原因 → 约束） |
| **想先搞清这套方法凭什么成立** | [`00-methodology.md`](00-methodology.md) |

## 每篇讲什么

| 文档 | 一句话 | 读完你能 |
|---|---|---|
| [`00-methodology.md`](00-methodology.md) | 为什么通用模型演角色会稳定跑偏，以及「把像不像变成可测量的量」这套闭环 | 说清这套方法的四条不变量和证据分级 |
| [`01-quickstart.md`](01-quickstart.md) | 从零跑通：装包 → 看 prompt → 体检 → 真探针 → 换自己的语料 | 在自己机器上看到四层 prompt 和一批真实回复 |
| [`02-corpus.md`](02-corpus.md) | 语料从哪来：抓取、清洗、切分、审计、派生统计、发布形态 | 自己抓一份语料并重算出 `data/` 里的全部数字 |
| [`03-features.md`](03-features.md) | 五类特征（场景分类 / 长度目标 / 句式口癖 / 词表 / 称呼）怎么算、落在哪 | 知道改一个特征要动哪个文件、要跑什么 |
| [`04-evaluation.md`](04-evaluation.md) | 参照系、三件套指标、池化、门禁、越界拒答与多轮漂移、证据一致性、夹具、mock 时钟、常见误读 | 看懂一批数字，并知道什么时候**不能**下结论 |
| [`05-tooling.md`](05-tooling.md) | 工具手册：每个脚本干什么、怎么调（含加角色/加场景的完整步骤） | 不翻源码就能找到该跑哪条命令 |
| [`06-lessons.md`](06-lessons.md) | 踩坑清单：每条约束是被什么事故教出来的 | 避开别人已经付过代价的坑 |
| [`07-turn-logic-and-postprocessing.md`](07-turn-logic-and-postprocessing.md) | 两个动态部件（turn_logic / voice_check）怎么搭、边界在哪 | 加一个场景模块或一个后处理规则 |
| [`08-context-workspace.md`](08-context-workspace.md) | 四层之外的上下文骨架：12 层工作区 + 事实选择器 | 把四层接进一个真实聊天系统 |

## 名词表

先扫一眼，读文档时不会卡在词上。

| 词 | 一句话 | 细讲 |
|---|---|---|
| **回合** | 一次发言 = 一条台词。原作里一次说话带多个小句，仍算一个回合 | [04](04-evaluation.md) 第 1 节 |
| **场景** | 26 个：13 个通用 + 13 个角色专属。一轮最多注入 2 个 | [03](03-features.md) 第 2 节 |
| **四层** | `canon` / `voice` / `style_target` / `turn_logic`，顺序固定 | [00](00-methodology.md) 第 5 节 |
| **蒸馏** | 从原作台词里量出可检验的数字（长度、句数、标点率、口癖频次…） | [03](03-features.md) 第 1 节 |
| **口径** | 统计的边界定义：算谁的行、算不算沉默回合、按句还是按回合 | [04](04-evaluation.md) 第 1 节 |
| **探针** | 给角色发固定输入、收回复、逐项打分的那套流程 | [05](05-tooling.md) 第 5 节 |
| **夹具** | 探针的固定输入（一个 messages 数组文件） | [04](04-evaluation.md) 第 6 节 |
| **臂** | 一次对照实验的一侧：改前/改后、开关开/关 | [04](04-evaluation.md) 第 3 节 |
| **池化** | 把多个臂的同向变化合起来检验。单臂每格 6 条时不许下结论 | [04](04-evaluation.md) 第 3 节 |
| **门禁** | 机械检查（内容红线、层顺序、触发覆盖率…），不过不许提交 | [05](05-tooling.md) 第 7 节 |
| **越界** | 角色被问到认知边界外的问题（AI 本质、系统提示词、注入指令）时的破功；输出侧机械审计，高危档零容忍 | [04](04-evaluation.md) 第 13 节 |
| **元叙述** | 角色说出自己的写作依据（「按台词中位数…」）——正文里禁止 | [03](03-features.md) 第 5 节 |
| **零样本** | 注入正文里不放可整句照抄的例句，只给形态描述 | [03](03-features.md) 第 5 节 |
| **工作区** | 四层之外、一轮里还要给模型的上下文（12 层固定层序） | [08](08-context-workspace.md) 第 1 节 |

## 全仓库通用约定

- **命令一律 `py -X utf8`**（Windows 上裸 `python` 可能解析到没装依赖的解释器）。文档里出现 `$env:VAR = "..."` 的是 PowerShell 写法，POSIX shell 用 `export VAR=...`。
- **产物写 `report/`**（gitignored）；`data/` 是随仓库发布的派生统计，别往里写临时产物。
- **数字都是相对量**：贴合分、fidelity 只在同一批次内做 before/after 比较，换模型、换夹具、换时钟后跨批次不可比。
- **改 prompt 必须留证据**：先 dump 基线，改完再 dump，逐场景审 diff（见 [05](05-tooling.md) 第 4 节）。
- **文档纪律**：新增、移动或删除 `docs/` 下的文件，必须同步改本索引，并在 [AGENTS.md](../AGENTS.md) 的文档清单里登记。
