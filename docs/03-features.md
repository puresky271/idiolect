# 蒸馏出哪些特征，怎么算，落在哪

> 从特征表定位计算脚本、发布数据与 prompt 落点。修改前检查对应章节的约束，修改后按末尾验证表验收；方法依据见[方法总纲](00-methodology.md)。

**目录**：[1 五类特征一览](#1-五类特征一览) ｜ [2 场景体系](#2-场景体系) ｜ [3 每场景长度目标](#3-每场景长度目标) ｜ [4 口癖、句式、词表](#4-口癖句式词表) ｜ [5 写进 prompt 的措辞规范](#5-写进-prompt-的措辞规范) ｜ [6 触发词纪律](#6-触发词纪律) ｜ [7 改一层要跑什么](#7-改一层要跑什么)

## 1. 五类特征一览

| 特征 | 计算脚本 | 产物 | 落点 |
|---|---|---|---|
| 场景分类 | `tools/distill/scene_discover.py`、`validate_scenes.py` | 26 个场景原型与 key | `idiolect/scene_classifier.py`（判场景） |
| 每场景长度目标 | `scene_char_baseline.py` + `export_scene_targets.py` | `data/scene_char_baseline.json`、`idiolect/scene_length_targets.py` | 说话尺度层（命中场景时替换长度与句数） |
| 句式结构与口癖 | `style_features.py`、`verbal_tics.py`、`tic_profile.py`、`tic_by_scene.py` | `data/style_targets.json`、`tic_profile.json`、`tic_by_scene.json` | 语气 manifest + 说话尺度层 + 场景模块的 `tics` |
| 物品与话题词表 | `char_topic_vocab.py`、`scene_stats.py` | `data/scene_stats.json` 的 `vocab` 字段 | 场景模块正文里的具体名词 |
| 称呼 | `style_features` 的称呼统计 + 角色档案 | 语气 manifest 的称呼段 | 语气 manifest |

第五类在代码里没有独立产物，它是从统计里看出来的差异（谁怎么叫谁），写进 `idiolect/characters/*/voice.py` 的 `NICKNAME_RULE`，并由后处理层的称呼归一化保持口径一致。

场景分类单独算一层，是因为它是前四类的前提：长度目标、场景口癖、场景词表都按场景取。它也是**动态**的那一层，其余四类是静态或半静态。

## 2. 场景体系

26 个场景，13 个通用 + 13 个角色专属：

```text
通用：play_along affection crisis comfort low_mood wellwish schedule request
      fact_qa banter meta_language probe_stance third_party
角色：anon_beauty anon_sns / tomori_lyrics tomori_nature
      taki_music_pro taki_soft_spot taki_shift
      soyo_observe soyo_tea soyo_past / rana_guitar rana_food rana_cat
```

怎么发现的：给每个候选场景写一句原型台词，用句向量把原作台词检索到最近的场景上，再看这个划分是否稳定、场景之间是否可区分（`scene_discover.py` 做聚类与轮廓系数，`validate_scenes.py` 做冗余判据与纯度判据，报告写 `report/scene_separation.md`）。

这里有一个必须知道的口径限制：原型检索在短句语料上会被长度和风格带偏。`affection`（被示好）就撞上过这个：纯向量检索给灯抓来的原型近邻是「今天有体育课」。所以这个场景改用**反应词典锚定**（先按反应词筛出候选，再统计），锚定后的中位与向量检索同向，说明锚定没有扭曲分布。带偏离的场景要看 `scene_stats.py` 的 `char_side` 与 `watch` 字段。

### 2.1 顺序不变量

`idiolect/scene_classifier.py` 的 `_RULES` 与 `idiolect/general_scenes.py` 的层内顺序必须保持一致（比较的是通用场景在两边的相对顺序）。两边不一致的后果是：分类器判 A 场景、长度目标按 A 取，而 turn_logic 注入 B 的指引。这类 bug 不看代码看不出来。

守它的是 `tests/test_scene_turn_logic.py::test_layer_order_matches_classifier_order`。

注意覆盖面：`_RULES` 有 25 条（13 通用 + 12 角色专属），26 个场景里的 `soyo_observe` 没有分类器规则——它在 `idiolect/characters/soyo/turn_logic/scenes.py` 里由场景模块自己的触发词处理，长度目标仍可从 `scene_length_targets.py` 取到（但运行时不会由分类器判给它）。

## 3. 每场景长度目标

两层结构：

- **全局**：`data/style_targets.json` 里每角色一组标量（中位字数、p90、句数、小句数、六个标点出现率、自称率、高频语气词）。运行时由 `idiolect/style_target.py` 的手抄表 `STYLE_TARGETS` 提供。
- **场景级**：`idiolect/scene_length_targets.py` 的 130 个 `(角色 × 场景)` 目标（`median` / `p90` / `sent` / `n` / `cn`）。命中场景时替换长度与句数两行，其余行（句末标点率、自称、硬检查）仍用全局值。

回落路径：`get_scene_target(char, scene)` 没有该组合时返回 `None`，`build_style_target_block` 退回全局值。生成侧 `MIN_N = 20`，样本不足的组合直接不导出（当前丢弃 0 个）。

同一角色在不同场景的长度差 1.6~2.6 倍，这就是必须有场景级目标的原因。全局数字在短场景过宽、在长场景过严。

`data/style_targets.json` 与手抄的 `STYLE_TARGETS` 是两份东西：前者是脚本产物，后者是运行时读的那份。导出脚本刻意**不过滤 split**（写 prompt 用的数字样本多一份更稳），而评测画像只用 train，两者 n 不同（cn.anon 1579 vs 1244）。

## 4. 口癖、句式、词表

**口癖画像** `data/tic_profile.json`：每角色一组条目，字段 `tic`、`count`、`per_10k`、`line_share`、`start_share`、`endpoint`、`specificity`、`top_other`、`top_other_per_10k`。

`specificity` 是用来找出「这个人说、别人不说」的词：本角色每万字频次与最常说的另一个角色的比值。`count < 3` 的候选不报，条目按 `specificity` 排序。声明的口癖与实测的差异靠它核对（候选表里带 ★ 的是已写进语气 manifest 的那些）。

**场景口癖** `data/tic_by_scene.json`：114 个 `角色|场景` cell，字段 `tic`、`count`、`per_10k`、`base_per_10k`、`lift`。门槛是 cell 内出现 ≥ 5 次且 `lift` ≥ 1.4，`lift` 定义为该场景每万字频次比该角色全局每万字频次。

场景模块的 `tics` 字段**只能**填这里的显著项（`SceneModule` 的 docstring 写明了这条约束）。凭感觉填的口癖会让场景指引变成风格污染。

**句式结构**来自长度分布本身：中位与 p90 字数、每回合句数与小句数、句末标点占比（省略号 / 感叹号 / 问号 / 句号）、自称出现率、起手形态（名词直出 / 语气词 / 疑问）。这些数字进说话尺度层，起手形态进语气 manifest。

**物品与话题词表**在 `data/scene_stats.json` 的 `vocab` 字段里，用途是给场景模块的正文提供「这一轮可以抓的具体东西」。它进的是正文里的名词示例，不是清单形式——清单会让模型当成待办表逐条念。

## 5. 写进 prompt 的措辞规范

这一节是整套方法里最容易被忽视、代价也最大的部分。

**不允许可整句照抄的例句。** 改前的生产臂实测（旧批次记录，产物未随仓库发布）：22%~27% 的回复逐字复述了正文里的句子，最长公共子串 22 字。最重的几格记在 `tests/test_scene_turn_logic.py::NoReusableExampleSentencesTests` 的 docstring 里，两份记录的**口径不同**别混读：`rana.cat_talk` 是「6 条回复里 5 条整条完全相同」，同时「6 条都逐字带上了那句正例」。

当前批次的对照值可以自己跑出来：`_copy_audit.py` 在 `repo_standalone` 上是**复述率 1%、最长公共子串 3 字**（抄的那 3 个字是口癖「诶……」，不是例句），与 README 的「真实输出」一节一致。

规则按这个顺序收紧过三代：

1. 第一代禁「大于 8 字的整句」。实测仍有 3~5 字的碎片被搬走（`「屋顶。」`，4/6 条）。
2. 第二代改成**示例行里只允许口癖长度的引用，阈值 `MAX_LEN = 4`**。口癖是角色属性（语气 manifest 里本来就有），更长的片段都是例句。
3. 第三代补上扫描范围：反例行、口癖行、标「原话」的 canon 引用行要按标记识别并跳过，否则门禁要么漏扫要么误报。

门禁是 `tests/test_scene_turn_logic.py::NoReusableExampleSentencesTests`：抽 `「」` 里的内容，剥掉标点与强调标记，超过 4 字就失败；行匹配 `形态示例|正例|参考`，跳过 `口癖|原话`。

长度控制改由**字数上限 + 句数**承担。代价是实测过的：零样本用词之后长度贴合度从 0.512 掉到 0.461（旧批次记录，产物未随仓库发布），这个代价是自愿接受的。

**canon 原话改成「从你自己的档案里取」。** 角色档案里有真实台词（例如爱音对乐奈的评价），那些台词对角色是重要的具名锚点。规矩是：不在注入正文里复述它们，而是让模型从档案里取。这样既保留锚点，又不制造新的照抄源。

**字数预算的作用域必须显式。** 写「N 字上下、一到两句」会被读成每句的上限，模型每句都写满，总长翻倍。正确写法是「**两句合计** N 字（不要每句都写满）」。

**元叙述不许进角色可见文本。** 「语料」「实测」「中位」「p90」「基线」「lift」「频次」「统计」这些词一旦进 prompt，模型有概率顺着它们谈自己的设定。禁词表在 `tools/gates/voice_meta_gate.py`，扫描范围含 canon、语气 manifest、说话尺度块与 turn_logic 渲染结果。

## 6. 触发词纪律

场景模块的触发词是**正则片段**，不是字面量。`SceneModule.pattern()` 会编译它们，因此不能再 `re.escape`——踩过一次：「(昨天|上次)」被转义成字面量，与逻辑里两个 lookahead 全部失效，场景静默不触发。

三条具体纪律：

1. **触发词要有语料实证**。`tools/distill/verify_triggers.py` 逐词查原作出现率，语料里不存在的词不许当触发词（「排练」「拨片」「大吉岭」这类看起来合理但语料里没有的词被挡下过）。
2. **容易误触发的用与逻辑**。`affection` 要求「示好信号」与「第二人称指向」同时命中，避免把第三方语境一起吃掉；实现方式是 `all_required=True` 加 lookahead。
3. **注入层可以比分类器更紧**。分类器把「你是不是又睡着了」判成 `probe_stance`，注入层必须挡住它——它有专门的场景模块，不该被「试探」指引覆盖。`test_new_scenes_fire_and_probe_stance_is_guarded` 守着这条。

去重与预算：同一场景在同一 session 内只注入一次（`scene_engine._mark_fired`），一轮最多注入 2 个场景（`max_blocks`）。第二轮起不重复注入，是为了避免同一段指引在长会话里反复出现、把语气压成一个方向。

查看尺寸不算一轮真实对话。`assemble.layer_sizes` 在 `scene_engine.isolated_session_state()` 中运行：按需复制去重表和计数/余波表，保留当前状态供观察，退出后丢弃诊断修改。连续查看不会消耗下一次真实装配的场景。真实 `build_messages` 和 `build_system_prompt` 仍正常推进状态。

隔离作用域用于同步诊断，不是跨状态表的原子事务；它不交换或回滚真实表，因此不会抹掉另一线程的更新。不要将该作用域当作后台任务共享的会话，也不要在诊断中启动需要继承真实状态的异步工作。

## 7. 改一层要跑什么

| 改动 | 至少跑 |
|---|---|
| 注入正文（通用场景 / 深模块） | `_gen_scene_check.py`、`_tl_deep_check.py`、`tests/test_scene_turn_logic.py` |
| 语气 manifest 或 canon | `voice_meta_gate.py`（含四个面的扫描） |
| 说话尺度或场景目标 | `export_scene_targets.py` 重跑 + `dump_prompt.py --phase current` 在编辑前后分目录对比 |
| 分类器或场景 key | `validate_scenes.py`、顺序不变量的测试、`offline_smoke.py` |
| 任何会进 prompt 的改动 | `offline_smoke.py` 全套，然后 `probe_runner.py --assemble --turn-logic` 跑一轮真探针 |

探针跑完的收尾见 `docs/04-evaluation.md`；工具参数见 `docs/05-tooling.md`。

---

**上一站**：[`02-corpus.md`](02-corpus.md) ｜ **下一站**：[`04-evaluation.md`](04-evaluation.md) ｜ **索引**：[`README.md`](README.md)
