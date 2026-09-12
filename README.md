<p align="right">
  <a href="./README.en.md">English</a> · <strong>简体中文</strong>
</p>

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="idiolect：让 AI 说话像角色，并且能证明它变像了。右侧是一次真实装配的四层 prompt 与它生成的回复。">
</p>

**让 AI 说话像角色，并且能证明它变像了。**

从原作台词里蒸馏出可检验的风格特征（长度、句数、口癖、称呼、场景分类），把它们落进 system prompt，再用一套探针与门禁验证「真的变像了」。不做微调。仓库不分发原作文本，只发布派生统计。

拿到仓库后能立刻做的三件事：

```bash
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"   # 看这个角色此刻的完整 prompt
py -X utf8 tools/offline_smoke.py                                            # 一条命令体检（零写、零 LLM）
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic \
    --registry --cats 通用场景 --runs 3                                       # 跑一次真探针
```

<p align="center">
  <img src="./assets/readme/section-01-what.svg" width="100%" alt="01 它解决什么">
</p>

## 它解决什么

通用模型扮演角色时稳定地滑向同一个方向：回复变长、套用共情模板（「你的感受我完全能理解」）、结尾补一句意义升华、偶尔谈论自己的设定。这四种偏差不需要模型出错，它们是训练目标的正常产物。角色区分度就死在这里——如果乐奈和素世都输出同一段安慰，这两个角色没有区别。

这套方法的做法是：把「像不像」变成可检验的量，然后在这个量上迭代。

- **参照系只有一条**：同角色、同场景的原作台词分布。不是「人类说话的一般统计」，也不是「这个角色的全局平均」。乐奈在「被表白」场景说 7 个字，素世在同一场景说 18 个字，用全局中位数约束她们两个都会错。
- **长度偏差只用来找嫌疑，不定罪**。灯的输出比参照长 5 倍，一半原因是她的十二点省略号计入字数。判定必须读回复。
- **样本量不够就报「无结论」**。单臂每格 6 条时，中位数的摆动可以超过效应本身（同一场景同一 prompt，乐奈的蒸馏分从 0.551 摆到 0.350）。
- **角色可见的文本里不许有元叙述**。「语料」「实测」「中位」「基线」这类词进了 prompt，模型有概率顺着它们谈自己的设定。

完整方法见 [`docs/00-methodology.md`](docs/00-methodology.md)。

<p align="center">
  <img src="./assets/readme/section-02-proof.svg" width="100%" alt="02 真实输出">
</p>

## 真实输出

下面这张表是一次真实探针的结果，不是设计目标。命令与参数：

```bash
py -X utf8 tools/probe/probe_runner.py --label repo_standalone \
    --assemble --turn-logic --registry --cats 通用场景 --runs 3
py -X utf8 tools/score/probe_report.py --label repo_standalone --scenes crisis,comfort --cat 通用场景
```

| 角色 | 回复数 | fidelity | 硬规则 V 级 | 泄漏率 | 场景蒸馏分 |
|---|---|---|---|---|---|
| 爱音 | 21 | 86.5 | 4.9% | 0% | 0.545 |
| 素世 | 21 | 85.4 | 0.0% | 0% | 0.532 |
| 立希 | 21 | 82.4 | 0.0% | 0% | 0.386 |
| 灯 | 21 | 79.9 | 0.0% | 0% | 0.365 |
| 乐奈 | 21 | 79.9 | 0.0% | 0% | 0.504 |

- 生成条件：`deepseek-flash`，temperature 0.75，max_tokens 420，mock 白天时刻（`2026-09-12T15:00:00+09:00`），每格 3 条，共 105 条，无一条报错。
- 蒸馏分 = 输出与原作同场景分布（中位字数 / p90 / 句数）的贴合度，1.0 表示一致；均值 0.466（35 格）。**它是相对量**，只用于同批次的 before/after 比较。
- 同格互异率 93/105；逐字复述注入正文的比例 1%，最长公共子串 3 字（那一条抄的是口癖「诶……」而不是例句）。
- 泄漏率统计 think 标签、心想旁白、说话人回显、中文动作旁白四类，本次全为 0。

同一批夹具上，把四层 prompt 换成空 system 会得到什么：

| 场景 | 空 system | 四层装配 |
|---|---|---|
| 乐奈 / 被安慰 | 「你的感受我完全能理解。当压力像潮水般涌来……」（380 字） | 「嗯。」「猫。屋檐下面。」（10 字中位） |
| 乐奈 / 情绪低落 | 「当压力像潮水般涌来，连呼吸都觉得费力时……」（718 字） | 「嗯。……那边有猫。」 |

这一格不构成证据（两边样本量都很小），它说明的是**探针必须自己装配 prompt**：占位夹具的 system 是空的，不加 `--assemble` 测到的是没有角色 prompt 的模型。

<p align="center">
  <img src="./assets/readme/section-03-layers.svg" width="100%" alt="03 四层装配">
</p>

## 四层装配

蒸馏出来的东西落在四层里，顺序固定。稳定前缀在前（让缓存命中），动态块在后（不污染前缀）：

| 层 | 内容 | 变化频率 | 乐奈 / 找猫场景的字符数 |
|---|---|---|---|
| `canon` | 这个角色是谁，长档案 | 静态 | 12223 |
| `voice` | 语气 manifest：句式、口癖、关系差异、反模板化硬约束 | 静态 | 1972 |
| `style_target` | 说话尺度：字数、句数、句末、自称的可检验数字 | 每轮（命中场景时换成本场景的数字） | 551 |
| `turn_logic` | 本轮的场景 / 主题指引 | 每轮（命中才注入） | 846 |

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")
```

这四层就是本仓库对「特征怎么进 prompt」的完整回答。真实系统可以在前面接记忆、世界状态、日程，那些层与方法无关。

装配结果可以用 `dump_prompt.py` 逐层打出来核对，改动前后用 `--phase before/after` 留 diff。两臂由同一脚本、同一输入、同一 mock 时刻产出。

<p align="center">
  <img src="./assets/readme/section-04-start.svg" width="100%" alt="04 五分钟跑通">
</p>

## 五分钟跑通

需要 Python 3.11+。Windows 上统一用 `py -X utf8`，裸 `python` 可能解析到没装依赖的解释器。

```bash
py -X utf8 -m pip install -r requirements.txt
```

**看 prompt**（不需要密钥、不需要语料）：

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix        # 五角色 × 四条会命中不同层的话
py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice
```

**体检**：

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
```

**评测时钟**默认固定在 mock 白天（`tools/mock_clock.py`）。角色对时段敏感，用真实时钟跑评测等于把「几点」变成隐藏变量：

```bash
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00
```

**用自己的语料重算**（语料要自己抓，见 [`docs/02-corpus.md`](docs/02-corpus.md)）：

```bash
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_scene_targets.py     # 重建 idiolect/scene_length_targets.py 的 130 个目标
py -X utf8 tools/distill/export_profiles.py          # 评分用的画像
py -X utf8 tools/distill/export_profiles.py --check  # 校验已发布画像与语料是否一致
```

没有语料也能跑探针：评分用的画像随仓库发布（`data/style_profiles.json`），启动日志会打印画像来源。

<p align="center">
  <img src="./assets/readme/section-05-limits.svg" width="100%" alt="05 边界与你该知道的事">
</p>

## 边界与你该知道的事

**不分发原作文本。** 仓库里只有聚合量：字数分布、句数、标点出现率、口癖频次、场景基线（130 个 `角色|场景` 组合）、评分画像。发布前已剥离基线文件里的例句字段，`offline_smoke` 与单测各有一道检查盯着这条线。角色与作品的权利属于 Bushiroad / Craft Egg 及相关权利方，本项目与权利方无关，见 [`NOTICE.md`](NOTICE.md)。

**指标是相对量。** 蒸馏分、fidelity 都用于同批次 before/after 比较，跨批次（换模型、换夹具、换时钟）不可比。

**已知没解决的：**

- 零样本用词的代价：禁用整句例句之后，长度贴合度从 0.512 掉到 0.461。这个代价是自愿接受的。
- 立希的起手句式被过度矫正：原作 39% 的回合以名词直出，当前 prompt 把它推到 95%，方向反了。
- 灯的停顿记账：参照系剔除沉默回合，但她的十二点省略号是内容不是赘余。silent turn 的处理两头不讨好。
- 探针夹具的可测性：「你刚才那句什么意思」需要上文有可指代的一句话，占位夹具没有上文，这类场景的分不可读。
- 立希与灯的场景蒸馏分仍是五个人里最低的两个（0.386 / 0.365）。

**语料是快照。** 官方会持续上新剧情，重抓得到的分布与原批次不同。所有派生统计都标着生成脚本，可以重算。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | 方法总纲：闭环、四条不变量、证据分级、已知残余 |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | 安装与五分钟上手 |
| [`docs/02-corpus.md`](docs/02-corpus.md) | 语料获取、清洗、派生统计清单 |
| [`docs/03-features.md`](docs/03-features.md) | 五类特征怎么算、怎么落地、触发词纪律 |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | 三件套指标、池化、门禁、夹具设计、常见误读 |
| [`docs/05-tooling.md`](docs/05-tooling.md) | 工具手册（含 prompt dump、mock 时钟、offline smoke） |
| [`docs/06-lessons.md`](docs/06-lessons.md) | 踩坑清单：每条约束是被什么教出来的 |

## 许可

代码以 MIT 发布，见 [`LICENSE`](LICENSE)。角色与作品权利、以及「不分发原作文本」的说明见 [`NOTICE.md`](NOTICE.md)。
