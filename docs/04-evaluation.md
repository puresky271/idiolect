# 评测：怎么知道它变像了

> 讲什么：评测的参照系、三件套指标、池化与功效、两道门禁、夹具与时钟、常见误读。 ｜ 前置：手上有探针产物（`report/probe_<label>.jsonl`）时读它才有意义。

**目录**：[1 参照系](#1-参照系) ｜ [2 三件套指标](#2-三件套指标) ｜ [3 单臂不够，池化才算数](#3-单臂不够池化才算数) ｜ [4 机械门禁](#4-机械门禁) ｜ [5 prompt diff 门禁](#5-prompt-diff-门禁) ｜ [6 夹具设计](#6-夹具设计) ｜ [7 mock 时钟](#7-mock-时钟) ｜ [8 常见误读](#8-常见误读) ｜ [9 发布数据的可重建性](#9-发布数据的可重建性) ｜ [10 样本外验收](#10-样本外验收holdout) ｜ [11 验收门禁](#11-验收门禁任一退化即-fail) ｜ [12 A/B 盲评](#12-ab-盲评)

## 1. 参照系

评测里唯一的参照物是 `data/scene_char_baseline.json`：原作里**同一角色**在**同一场景**说过的台词分布，按 `角色|场景` 建键，130 个组合。切分口径是「一个回合 = 一条台词」，不是「一句话」：原作里一次发言可能带多个小句，那算一个回合。

基线里剔除了沉默回合（只有标点或空白的台词）。这个选择有代价，见 `docs/00-methodology.md` 的「已知残余」：灯的 12 点停顿是内容，却被算作沉默。

## 2. 三件套指标

跑完探针之后必须一起看三个量。少看一个都会得到错误结论。

### 2.1 `composite`：探针汇总表的头号指标（2026-09-13 起）

`probe_runner` 汇总表以 **composite** 领衔（`style_features.composite_score`）：

```
composite = 0.65 × fidelity（风格保真） + 0.35 × anchor_score（内容锚点）
anchor_score = min(输出锚点密度 / anchor_ref, 1.0) × 100
```

为什么不能再只看 fidelity：它只量长度/句数等分布拟合，**测的是「听话」不是「像」**。
2026-09-13 外部评审用本仓库的评分函数跑构造样本证实：一段完全出戏的通用助手腔
fidelity 84.9、distill 0.606，**高于**真像乐奈的样本（82.0 / 0.286）；接线 composite
后同一批样本的排序翻正且差距拉开（真在安慰 89.9 > 合格短句 85.1 > 助手腔 71.4 >
语义空白 49.1，复算留档 `report/eval_fix_evidence.md`）。
这条判别力由 `tests/test_eval_gates.py::ScoreArmCompositeTests` 钉成契约。

`anchor_ref` 的三个来源（按优先级）：① gold 画像自带的 `anchor_density` 字段
（`export_profiles.py` 实测导出，该角色自身常态，不跨角色硬比）；② 画像缺字段时
从 `data/scene_char_baseline.json` 按 n 加权派生；③ 1.0 兜底（只是最后防线）。
探针启动时 `[probe] gold 画像来源 = …｜anchor_ref 来源 = …` 那行会写明走了哪条。

fidelity 保留为对照列：它与 composite 背离时（fidelity 涨、composite 不涨），
说明改动在压长度而不是在塑角色。

### 2.2 `scene_distill`：分布级贴合度

逐 (角色, 场景) 格比较输出与原作同场景的分布：

| 维度 | 含义 |
|---|---|
| `len_ratio` | 输出中位字长 / 原作同场景中位字长 |
| `len_p90_ratio` | 输出 p90 / 原作同场景 p90 |
| `sent_ratio` | 输出句数 / 原作同场景句数 |
| `anchor_ratio` | 输出锚点密度 / 原作同场景锚点密度（诊断列，不进复合分） |
| `distill` | 复合分，1.0 表示与原作同场景一致 |
| `excess` | 本场景总偏离 − 该角色本次所有场景的平均总偏离 |

`excess` 是最有用的那一列：它回答「这个场景是不是比她自己平时更跑偏」，正值得高的场景就是下一轮要改的地方。

`anchor_ratio` 被降级成诊断列，原因记在脚本头部：锚点密度是 hits/chars 的比值，短句场景的分母极小，基线在 0.19~3.48 之间乱跳，而模型输出稳定在 4.0~4.4，于是它变成恒定惩罚，把 13 个场景里的 7 个压成 0.000。锚点本身有信息（模型每百字锚点约为原作的 2.3 倍），但那是全局结论，不能用来区分场景。

### 2.3 `_repeat_rate`：同格重复度

同一格 6 条回复里有多少条互不相同。这个量专门抓「复读」：长度指标看不出「6 条里 5 条一模一样」。

### 2.4 `_copy_audit`：逐字复述审计

把注入正文里**示例行**的引号内容抽出来，逐条回复做逐字包含判断，另算最长公共子串（≥4 字算近似复述）。

抽取规则里有两条必须留意：只看带「形态示例 / 正例 / 参考 / 示例」标记的行；口癖提示行要排除，因为口癖本来就是要角色说的。

## 3. 单臂不够，池化才算数

逐格 6 条的摆动大于效应本身。`_pool_arms.py` 把同一批夹具的多个臂合并成大样本，再与基线臂比较，输出池化后的均值与逐格改善数。

读池化结果的方式：看**改善格数与退化格数的比例**，再看池化均值差。一次典型的池化结果长这样（宿主工程的旧批次记录，臂产物未随仓库发布）：7 个注入臂的均值从 0.326 到 0.483（Δ +0.157，20 格里 15 格改善）；换成另外 15 条夹具，Δ −0.004（8/15 改善）。前者是「改动方向对」，后者是「换一批夹具就没了」，两句话必须一起说。要得到自己批次的两行数，用 `_pool_arms.py --off-labels <臂> --on-labels <臂>` 重跑。

## 4. 机械门禁

门禁不依赖样本量，可以进 CI。当前四道：

| 门禁 | 查什么 |
|---|---|
| `voice_meta_gate.py` | 角色可见文本里的元叙述词（扫 canon / voice / 说话尺度块 / turn_logic 渲染结果） |
| `_gen_scene_check.py` | 通用场景注入正文的规范：无可整句照抄的例句、正反例标记齐全 |
| `_tl_deep_check.py` | 深模块注入正文的同一套规范 |
| `audit_role_packages.py` | 角色包结构与注册表一致性 |

外加 `tests/test_scene_turn_logic.py` 里的 `NoReusableExampleSentencesTests`：它逐行扫注入正文，限制「例句」长度，并跳过带反例/口癖/原话标记的行。这个测试有过三次盲区（只看标记行、只看示例行、把反例误判），每次都是因为**扫描范围**而不是规则本身。

## 5. prompt diff 门禁

改动任何会进最终 prompt 的模块，都必须产出 before / after 两份 dump，用相同输入与相同 mock 时刻：

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase before
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase after
```

`--phase before` 把深模块与通用场景层的 env 开关全部置 0（改动前行为），`after` 用当前代码。两臂由同一脚本、同一输入产出，不允许「改完之后手写一个 before」。

审查 diff 时逐项确认：层顺序、块边界是否闭合、触发是否只在该触发的场景里发生、无关场景零漂移、预算未超。

顺带一条容易踩的坑：从调用方一侧 dump 真实运行路径时可能看不到 turn_logic——它在开发者模式下按设计不触发。这类「门禁看不到目标路径」的问题在这条链上出现过两次，所以 `tools/gates/dump_prompt.py` 直接调装配层，绕开模式判断。

## 6. 夹具设计

探针夹具是一份真实 messages dump 加一次替换：把最后一条 user 换成待测问题，system 段与历史完全不动。这样 before/after 的差异只可能来自被改的那一层。

夹具要满足两个条件才算可测：

1. **有可指代的上文**。「你刚才那句什么意思」需要上文里真的有一句话可以指；占位夹具没有上文，这个场景的分就不可读，不能拿来当证据。
2. **system 段要么自带、要么现装配**。本仓库的占位夹具 system 为空，必须加 `--assemble` 现场装配四层；否则模型收到空 system，回复会退化成通用助手腔，此时测的是「没有角色 prompt 的模型」。

## 7. mock 时钟

所有评测跑在固定的 mock 时间下：默认 `2026-09-12T15:00:00+09:00`，一个普通的白天。理由不是洁癖：角色对「现在」敏感，夜里会命中犯困、深夜类场景，把「今天是几点」变成实验里的隐藏变量。

```bash
py -X utf8 tools/mock_clock.py                       # 看当前生效时间
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00   # 打印要设的变量行（不会改当前 shell）
```

这条命令只**打印**要设的环境变量；把它贴进 shell 才生效（子进程改不了父进程的环境）。想跑真实时钟就把值设成 `real`，此时探针会打印警告：这批数字不能与 mock 批次比较。

## 8. 常见误读

- **拿 `distill` 当绝对分**。它是相对量，只用于同批次 before/after。跨批次比较要先确认夹具、参数、模型、时钟都一致。
- **拿 fidelity 当「像不像」的证明**。fidelity 与注入的说话尺度同源（注入「7 字」再测「是不是 7 字」），本质是对指令的合规性检查；纯助手腔能拿到 84.9。「像不像」看 composite + 盲评（第 2.1、12 节）。
- **拿单场景的改善宣布成功**。单格的摆动可以超过效应本身。
- **只看长度**。长度贴合可以用「变冷淡」刷出来，所以必须同时看锚点密度与同格重复度。
- **只信一个复合分**。composite 本身也是复合分，立希名词直出率 39%→62% 这类退化照样漏；验收要过第 11 节的多指标门禁——任一独立指标退化即 FAIL。
- **把门禁跑绿当成覆盖面完整**。门禁的价值等于它的扫描范围，`voice_meta_gate` 漏掉说话尺度块就是现成的例子。
- **拿一次运行当稳定结果**。同一份语料跑两次都要能给出同一个文件。判定方式是**两个独立进程**的输出逐字节比较（`tests/test_tooling_contracts.py::test_logodds_is_deterministic_across_processes`），不是肉眼看。

## 9. 发布数据的可重建性

这是评测方法的一部分：如果发布出去的派生统计无法从语料重建，那么所有基于它的分数都无法复核。

判定标准：用同一份语料重跑生成脚本，产物的 **JSON 值、键序与键集合**与仓库里的文件逐字段一致。2026-09-13 实测六个文件全部满足（六条命令见 `data/README.md`）。为了达到这个标准修掉两处不确定性（词表并列项、top-N 截断的兜底排序）。

一个措辞边界：这是**内容级**判定，不是字节级。生成物与发布版可能在行尾与结尾换行上差一两个字节（Windows 上 Python 文本模式写 CRLF，`.gitattributes` 却声明 `eol=lf`），所以拿 `git diff` 是否为空来判断会误判——要逐字段比较。

诊断类报告（`scene_discover`、`validate_scenes`、`scene_distill`）只保证内容一致，并列项的先后不保证——它们不进 prompt，也不作为分数基线。

## 10. 样本外验收（holdout）

`build_gold.py` 按文本 hash 稳定切 20% 作 holdout，设计意图是「调参只能看 train 的分布，**验收用 holdout**」。但 2026-09-13 之前所有下游（基线、画像、口癖表）只读 train，holdout 零消费点——也就是说所有分数都是在「构造 prompt 目标所用的那份数据」上测的，是 in-sample 拟合度，不是泛化证据（外部评审第六节）。

现在消费闭环补上了：

```bash
# ① 用 holdout 台词建一套验收基线（不调参的人不看它）
py -X utf8 tools/distill/scene_char_baseline.py --split holdout --no-exemplars
#    -> report/scene_char_baseline_holdout.json

# ② 验收轮：用 holdout 基线给最终臂打分（产物名带 _vs_ 后缀，不覆盖 train 口径结果）
py -X utf8 tools/score/scene_distill.py --labels <验收批> \
    --baseline report/scene_char_baseline_holdout.json
```

纪律：holdout 基线只在**验收轮**使用。调参轮看 train 基线；拿着 holdout 的数字回头改 prompt，就把留出集又变成了训练集，这套机制就废了。

## 11. 验收门禁：任一退化即 FAIL

改完 prompt 要合并前，过 `tools/gates/accept_check.py`：

```bash
py -X utf8 tools/gates/accept_check.py --before <基线臂> --after <待验收臂>
```

四条指标**各自独立**判定，任一退化整体 FAIL（数据源都是已落盘的探针产物，不再调 LLM）：

| 指标 | 数据源 | 默认容差 |
|---|---|---|
| composite 均值 | `probe_<label>_summary.json` | 降 > 1.0 分 |
| distill 均值 | `scene_distill_<label>.json` | 降 > 0.02 |
| 硬规则 V 级率 | summary JSON | 升 > 1pp |
| 同格重复度 | probe jsonl 现场算 | 升 > 5pp |

容差都可用 `--tol-*` 调。设计原则：复合分（composite / distill）任一单独通过都**不够**——立希名词直出退化、「变冷淡刷分」这些真实事故全是单指标漏检。缺产物文件是 rc 2 的明确报错，半截证据不许当「通过」。

## 12. A/B 盲评

机械指标（composite / distill）之外，内容维度还需要正交信号——`tools/score/ab_blind.py` 把两臂回复按夹具配对、随机左右（按输入定种，可复现），出题给人或 LLM 判「哪段更像这个角色」：

```bash
# 出题：生成盲评 worksheet（不含臂名）+ 判卷 key
py -X utf8 tools/score/ab_blind.py --a <基线臂> --b <待验收臂>
# 人工判完（{item_id: "left"|"right"|"tie"}）后判卷统胜率
py -X utf8 tools/score/ab_blind.py --tally 答卷.json --key report/ab_blind_<a>_vs_<b>_key.json
# 或者 LLM 判卷（正交参考，不进机械门禁）
py -X utf8 tools/score/ab_blind.py --a … --b … --llm
```

`--llm` 的已知局限：judge 与被判方是同一模型时，结论是循环论证的弱信号——用它与人工盲评互相印证，不单独当证据。

---

**上一站**：[`03-features.md`](03-features.md) ｜ **下一站**：[`05-tooling.md`](05-tooling.md) ｜ **索引**：[`README.md`](README.md)
