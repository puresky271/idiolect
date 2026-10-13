# 升级指南：v0.1.2

> 讲什么：从 v0.1.0 升级到 v0.1.2 时哪些行为变了、旧 API 怎么迁移、版本与合同的演进规则、怎么写插件、评测能下什么结论、接下来做什么。 ｜ 前置：无；细节分别在 [`09`](09-evidence-grounding.md) 与 [`10`](10-long-context-stress.md)。

**目录**：[1 兼容性一览](#1-兼容性一览) ｜ [2 旧 API 迁移](#2-旧-api-迁移) ｜ [3 版本策略](#3-版本策略) ｜ [4 插件开发规范](#4-插件开发规范) ｜ [5 评测边界](#5-评测边界) ｜ [6 设计取舍](#6-本版的设计取舍) ｜ [7 路线图](#7-路线图)

## 1. 兼容性一览

| 面 | v0.1.2 的变化 | 旧用法是否照常 |
|---|---|---|
| `build_messages` / `build_system_prompt` / 四层装配 | 无变化（四层矩阵 dump 前后逐字节一致） | 是 |
| `build_workspace_messages`（不带证据） | 新增可选参数 `trace`；不传时输出与旧版逐字节一致 | 是 |
| 证据块渲染 | 新增一行用法说明；历史条目带 `[as_of]`；provenance 只渲染白名单键 | 渲染文本变了（有意） |
| `idiolect.workspace.EvidenceEnvelope` 等 | 实现迁到 `idiolect.evidence_contract`，workspace 继续 re-export | 是 |
| 无版本证据字典 | 走兼容层，行为不变，发 `DeprecationWarning` | 是（建议迁移） |
| CLI `list / prompt / sizes / showcase / chat` | 无变化 | 是 |
| CLI 新命令 | `capabilities / contract / bench / eval / run / compare / report / selftest` | — |
| `tools/gates/accept_check.py` | 精确检验的实现迁到 `idiolect.evals.stats`，原名字 re-export，数值逐位一致 | 是 |
| `probe_runner` 产物 | metadata `schema_version` 1 → 2，新增 `code` 与 `intervention`；新增 `--intervention` | 读旧批次照常，但旧批次不可自动比较 |
| `report_html.py` | 新增批次可比性判定；HTML 转义复用包内实现 | 是 |
| 运行时依赖 | 仍为零 | 是 |
| 开发依赖 | 新增 `lint` extra（钉死 ruff 版本） | — |

## 2. 旧 API 迁移

**证据上下文**：

```python
# 旧（仍可用，但会发 DeprecationWarning；缺失的 status 被当成 current）
from idiolect.workspace import TemporalEvidenceContext
ctx = TemporalEvidenceContext.from_dict({"current": [{"text": "…", "evidence_id": "e1"}]})

# 新（严格：缺字段、未知字段、悬空引用、私有路径都会报错）
from idiolect.evidence_contract import parse_evidence_context, validate_evidence_context
report = validate_evidence_context(raw)        # 不抛异常，收集全部问题
ctx = parse_evidence_context(raw)              # 有 error 级问题就抛 ContractError
```

迁移步骤：给字典加 `"schema_version": "evidence-context/v1"`；每条证据显式写 `status` 与稳定的 `evidence_id`；时间写成带时区的 ISO 8601；需要观察者可见性时加 `observer_id` 与条目的 `visible_to`；把评估用的期望、gold、隐藏值从证据里挪到评测任务的 `expect` / `oracle`；provenance 里不要放路径、数据库位置或评估字段。用 `python -m idiolect contract validate <文件>` 检查。

**provenance 渲染**：旧实现把所有 provenance 键照抄进 prompt。现在默认只渲染 `source` / `modality`；需要别的键时在合同里声明 `permissions.render_provenance_keys`。

**宿主系统接入**：不要再把宿主的字典直接塞进 `evidence_context`。导出成 `explicit-snapshot/v1`（已脱敏、带权限声明、status 由宿主投影），用 `ExplicitSnapshotAdapter` 转换，再传给 workspace。

## 3. 版本策略

- **包版本** `idiolect.__version__`：补丁位用于不破坏合同的修复与新增（本版 0.1.2 只新增模块与可选参数，旧调用不变）；破坏现有调用或渲染结果的改动进次版本号，并在本篇登记。
- **合同版本**（`evidence-context/v1`、`explicit-snapshot/v1`、`benchmark-suite/v1`、`response-set/v1`、`labels/v1`、`eval-results/v1`、`experiment-manifest/v1`、`long-context-plan/v1`）：字段的语义变化或新增必填字段 → 新版本号；解析器对不认识的版本**拒收**，不猜。
- **能力版本**（`idiolect capabilities` 里的 version）与 **scorer 版本**写进每次运行的 manifest；版本不同的两批默认不可比，除非把 `scorer` / `capabilities` 预注册为干预变量。
- **内置数据**：手写回放登记了生成时 suite 的 SHA-256；改了 suite 而没重录回放，测试与完整性检查会直接失败。重录前先确认回放仍然对应修改后的任务。

## 4. 插件开发规范

**adapter**（`idiolect.adapters.EvidenceContextAdapter`）：

- 有 `name` 与 `version`；`to_context(payload) -> AdapterResult`，无副作用；
- 只接收调用方显式交来的 mapping，不自行打开文件、数据库或网络；
- 不推导 current / history / unknown；不可见记录丢弃时只报告 ID 与原因；
- 输出必须通过 `validate_evidence_context`。

**评分部件**（`idiolect.evals.pipeline.Components` 的 `boundary` / `response` / `style` / `cleaner` / `assemble`）：

- 返回 `Check`（或同形状的字典），每项带 `applicability`、`status`、`reason`、分子分母、证据与 `scorer_version`；
- 空回复、报错、干跑占位绝不能给 `pass`（聚合层的完整性检查会抓）；
- 判不了就给 `needs_review`，不要猜；
- 自带的金丝雀会检验 `boundary` 与 `response` 能否翻转判决——新部件必须能通过 `idiolect selftest`。

**新任务类型或新能力**：先写契约测试，再在 `idiolect/capabilities.py` 登记（版本、输入合同、适用任务、scorer、fixture、依赖、覆盖与不覆盖），再加至少一个会被抓到的变异体与一个健康反控制。

**代码与注释风格**：`ruff check .`（钉死版本）与 `tools/gates/style_gate.py` 必须通过——模块 docstring 与公开函数 docstring 用简体中文，注释以 `# ` 开头，不写纯英文的说明性注释。

## 5. 评测边界

- 合成回放、干跑、单批次运行统计只描述链路，**不是**模型效果；
- 变异体被抓到 ≠ 自然缺陷检出率；
- family 数低于预注册下限时，PASS 只表示未检出违规；
- 机械匹配只认声明过的写法；未认证的表示算子（中文数字读法、繁简）走 `needs_review`；
- 模型 judge 是辅助证据，不改机械判定；
- 风格分与 grounding 分不合成总分；任何一轴的硬失败都不能被另一轴抵消；
- 跨模型、跨夹具、跨时钟、跨 scorer 的数字不可比，除非 manifest 判 comparable。

## 6. 本版的设计取舍

以下几处会影响使用体验或公共合同。本版按「推荐」落地，若要改，改动面都在列出的模块里：

| 取舍 | 选项 | 本版选择 |
|---|---|---|
| 无版本证据字典 | ① 直接拒收 ② 兼容层 + 弃用警告 ③ 静默兼容 | ②：旧调用不断，新协议不被掩盖（`evidence_contract.TemporalEvidenceContext.from_dict`） |
| provenance 渲染 | ① 全量照抄 ② 白名单 + 合同声明扩展 ③ 完全不渲染 | ②（`render_evidence_block`） |
| 评测代码放哪 | ① 进 runtime 包（标准库） ② 独立发行包 ③ 只放 tools/ | ①：装了包就能离线评测与自测；付费 runner 的 openai 依赖仍是可选 extra |
| wheel 环境缺风格评分模块 | ① 判 missing（FAIL） ② 判 N/A 并在门禁说明与 manifest 里列出 ③ 静默跳过 | ②：不算通过、不进分母，跨环境批次不会被自动比较 |
| needs_review 的退出码 | ① 与 FAIL 相同 ② 单独的 3 | ②：CI 里同样非零，但能区分 |

## 7. 路线图

**本版已实现并有测试**：证据合同与兼容层、显式快照 adapter、grounding 任务与双轴门禁、能力注册与四种模式、实验 manifest 与可比性、同链变异自测与健康反控制、长上下文生成器与计量、离线 inspect 报告、付费 runner 的显式 opt-in、wheel 无依赖安装验收、代码与注释风格门禁。

**尚未做（不应被当作已完成）**：

1. 真实模型的 grounding 与长上下文批次（需要预注册的 family 数达标，并显式付费）；
2. 人工盲评标签的采集与标注一致性统计；
3. 跨模型、跨 tokenizer 的长上下文对比；
4. 图像、音频、位置等模态的文本化适配器（属于上游；idiolect 只消费文本化证据）；
5. 未认证表示算子（中文数字、繁简）的认证与扩展；
6. 宿主系统侧的快照导出器（属于宿主；idiolect 只定义 `explicit-snapshot/v1` 的消费合同）。

---

**上一站**：[`10-long-context-stress.md`](10-long-context-stress.md) ｜ **索引**：[`README.md`](README.md)
