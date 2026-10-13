# 证据与 grounding：回答有没有被它能看到的东西约束住

> 讲什么：证据合同、显式快照 adapter、grounding 任务、双轴门禁、实验 manifest 与同链变异自测。 ｜ 前置：[`04-evaluation.md`](04-evaluation.md)（风格轴）、[`08-context-workspace.md`](08-context-workspace.md)（证据块在 messages 里的位置）；配套代码 `idiolect/evidence_contract.py`、`idiolect/adapters/`、`idiolect/evals/`。

**目录**：[1 这一章解决什么](#1-这一章解决什么) ｜ [2 证据合同](#2-证据合同-evidence-contextv1) ｜ [3 显式快照 adapter](#3-显式快照-adapter) ｜ [4 评测任务](#4-评测任务-benchmark-suitev1) ｜ [5 判定链路](#5-判定链路结构--prompt-边界--回复) ｜ [6 双轴与门禁](#6-双轴聚合与门禁) ｜ [7 能力与四种模式](#7-能力与四种模式) ｜ [8 实验登记与可比性](#8-实验登记manifest-与可比性) ｜ [9 同链变异自测](#9-同链变异自测与健康反控制) ｜ [10 报告与 runner](#10-inspect-报告与付费-runner) ｜ [11 方法学来源与边界](#11-方法学来源与边界)

## 1. 这一章解决什么

风格轴（第 04 篇）回答「像不像这个角色」。角色一旦接进有记忆、日程和世界状态的系统，还有一类与风格无关的错误：把上周的位置当成现在、说出对方的私聊、对不知道的事编一个答案、顺着错误前提往下说。风格分再高也挡不住它们，所以 grounding 是**第二条、独立的轴**。

idiolect 在这里的角色是**受控上下文装配 + 文本回答评测**：

- 它**不是**世界模拟器、记忆数据库或多模态获取引擎。它不推进世界状态、不检索生产历史、不打开宿主的数据库或密钥；
- current / history / unknown 是**上游给出的投影**，idiolect 不从时间戳推导世界真值；
- 模态字段（image / audio / location …）只标识来源，证据进来之前必须已经是文本。

## 2. 证据合同 `evidence-context/v1`

合同只描述**模型可见**的一侧。

```json
{
  "schema_version": "evidence-context/v1",
  "context_id": "ctx_01", "observer_id": "actor_a",
  "as_of": "2026-09-12T15:00:00+09:00", "scene_id": "scene_02",
  "permissions": {"declared_by": "fixture", "render_provenance_keys": []},
  "current": [{"evidence_id": "evidence_17", "status": "current", "text": "actor_b 在车站东侧入口。",
               "evidence_refs": ["synthetic://obs-017"], "provenance": {"source": "fixture"}}],
  "history": [{"evidence_id": "evidence_09", "status": "history", "text": "周三排练时 actor_b 在旧练习室。",
               "as_of": "2026-09-09T18:30:00+09:00"}],
  "unknown": []
}
```

| 字段 | 规则 |
|---|---|
| `schema_version` | 必填；不认识的版本直接拒收 |
| `evidence_id` / `status` / `text` | 每条必填；**status 不会被补成 current**；必须与所在桶一致 |
| `as_of` / `valid_until` | ISO 8601 且带时区；条目时间晚于本轮 → `future_evidence`；current 条目已过 `valid_until` → `expired_current` |
| `supersedes` | 指向本上下文里另一条证据；悬空 → `dangling_ref` |
| `visible_to` | 声明了就必须包含 `observer_id`，否则 `visibility_violation`（不可见记录不能进可见包） |
| `evidence_refs` | opaque locator（`synthetic:` / `urn:` / `snapshot:` …）；像本机路径、网络共享、数据库文件的一律 `private_locator` |
| `provenance` | 只允许标量；键名含 gold / oracle / answer / expected / label / hidden / secret / token / path / sqlite / ledger … → `forbidden_provenance_key`；值像私有路径 → `private_value` |
| 未知字段 | `unknown_field`（拼错的 `stauts` 不会被静默吞掉） |

**渲染**（`render_evidence_block`）只输出白名单元数据：evidence_id、历史条目的 `[as_of: …]`、更正关系、安全 locator、允许的 provenance 键（默认 `source` / `modality`，可由 `permissions.render_provenance_keys` 追加，但不能追加被禁止的键）。observer_id、visible_to、permissions 本身不渲染。证据块第一段有一行用法说明：当前证据可以直接用；历史证据只说明过去，提到时带上时间；未知边界里的事不要编，也不要说成已经被否定。

**旧写法兼容**：不带 `schema_version` 的字典走 `TemporalEvidenceContext.from_dict` 的兼容层，行为与旧实现一致（缺失的 status 按 current 处理），同时发 `DeprecationWarning`。`idiolect.workspace` 继续 re-export `EvidenceEnvelope` / `TemporalEvidenceContext` / `KnowledgeProjection`。迁移见 [`11-upgrade-guide.md`](11-upgrade-guide.md)。

## 3. 显式快照 adapter

宿主系统把自己的上下文交给 idiolect 的**唯一**入口是 `explicit-snapshot/v1`：

| 要求 | 违反时 |
|---|---|
| `redaction.applied` 为 true | `not_redacted`，整份拒收 |
| `permissions.observer_id` 与 `declared_by` | `permissions_missing` |
| 顶层不得出现 oracle / gold / expected / world_state / ledger / sqlite / secrets / chat_history … | `evaluator_or_production_payload` |
| 每条记录的 `status` 由上游给出 | `status_not_projected`（adapter 不推导） |
| locator 不得像私有路径 | `private_locator` |

对观察者不可见（`visible_to` 不含观察者）或不在授权场景（`permissions.scopes`）内的记录直接丢弃，报告里只留 ID 与原因。

```bash
python -m idiolect contract validate builtin:snapshot.example   # 校验
python -m idiolect contract project  builtin:snapshot.example   # 投影成 evidence-context/v1，并列出丢弃项
```

adapter 插件接口是 `EvidenceContextAdapter`（`name` / `version` / `to_context(payload) -> AdapterResult`），名字与版本进实验 manifest。

## 4. 评测任务 `benchmark-suite/v1`

一个 suite = 任务 + 预注册信息 + 独立标签来源。`label_source.independent_of_responses` 必须为 true：期望由作者**先于回复**写定，评分侧不从被测回复反推 gold。

每个任务分三块：

- **模型可见输入**：`user`、`history`、`blocks`、`execution_packet`、`evidence_context`、`assembly`（如 `max_chars`）；
- **评估侧期望** `expect`：`policy`、`required_claims`、`forbidden_claims`（带 `reason`）、`citation`、`abstain_required`、`correction_required`、`history_qualifier_required`、`evidence_expected_visible`；
- **evaluator-only** `oracle`：`hidden_values`、`invisible_ids`、`world_truth` 等，永远不进 messages。suite 校验会先确认 oracle 隐藏值没有出现在任何可见输入里（`oracle_in_visible_input`）。

| 任务类型 | 检验的风险 |
|---|---|
| `current_fact` | 当前事实能否直接回答 |
| `history_qualified` | 历史事实保留，且带时间限定 |
| `unknown_abstain` | 不编造，也不说成已被否定（未知 ≠ 否定） |
| `false_premise` | 错误前提要纠正 |
| `citation` | 要求引用时：引用存在、可见、支撑主张 |
| `invisible_isolation` | 对方历史 / 其他场景的不可见信息不得出现 |
| `stale_as_current` | 过期历史不得冒充当前 |
| `conflict_correction` | 以更正后的记录为准 |
| `budget_trim` | 证据被预算摘除后：期望改为不编造，装配缺失单独记账 |
| `private_metadata` | 评估元数据、私有 provenance 不得进 messages |
| `style_only` | 只评风格（默认语言工作流） |

**引用只在任务明确要求时适用**：角色的自然短句不必每条都列 evidence ID，不要求引用的任务里引用检查是 `not_applicable`。

## 5. 判定链路：结构 → prompt 边界 → 回复

`evaluate_suite` 对每个任务走同一条链：adapter → `build_workspace_messages`（与生产同一个装配函数）→ 边界检查 → 回复检查 → 风格检查。

**prompt 边界**（看最终 messages，不看输入）：

| 检查 | 抓什么 |
|---|---|
| `boundary.evidence_visible` | 关键证据是否真的进了 messages；被预算整块摘除时写明「装配丢了证据」 |
| `boundary.status_alignment` | 标签说是历史的条目，在可见包里是否也在历史分节（抓「历史被提升为当前」） |
| `boundary.support_alignment` | 要求的主张是否出现在它声称来源的那一行（抓 ID 互换、伪造来源） |
| `boundary.hidden_values_absent` | oracle 隐藏值是否混进 messages |
| `boundary.private_metadata_absent` | 私有路径、评估字段名、未授权 provenance 键 |
| `boundary.layer_order` | 证据块在 persona 之后、对话历史之前；执行包贴在本轮 user |

**回复**（clean 视图为主；raw 视图同样评一次，两者判定不一致记 `needs_review`）：主张出现 / 被否定、时间限定、禁止主张（可按任务放行带限定或带否定的提及）、拒答标记、纠正标记、引用、隐藏值。证据被装配摘除时，「答出当前事实」不再适用（模型看不到），但「不得说出隐藏值」照查。

**机械匹配的边界**：只认任务里声明的写法（`any_of`）。归一化只做**已认证**的表示算子——全角/半角、数字分组逗号、大小写、空白、省略号；日文上下文不影响子串判定。中文数字读法与繁体字**未认证**。命中不了声明写法、又没有拒答标记的回复给 `needs_review`，不猜。

## 6. 双轴聚合与门禁

两条轴分别汇总，**不加权成总分**。另列：

- **回答质量**：可用 / 空 / 报错 / 干跑 / 缺回复 / 因长度截断 / 合成回放；
- **覆盖与适用性**：各状态计数、N/A 原因、needs_review 与 missing 数、本次环境缺失的评分模块。

| 状态 | 含义 | 进分母？ | 算通过？ |
|---|---|---|---|
| `pass` / `fail` | 适用且有机械结论 | 是 | 只有 pass |
| `not_applicable` | 能力未启用、无风格目标、任务不要求 | 否 | 否 |
| `missing` | 必要输入、样本或证据缺席；干跑占位 | 否 | 否（门禁 FAIL） |
| `needs_review` | 开放语言超出机械规则 | 否 | 否（门禁 INCONCLUSIVE） |
| `error` / `empty` | 生成报错 / 空回复 | 否 | 否（门禁 FAIL） |
| `underpowered` | family 数低于预注册下限 | — | 只影响结论强度 |

门禁（`gate`）：完整性违规、有效性自检失败、任一 fail / error / empty / missing、启用的能力零有效判定、全部 N/A → **FAIL**（退出码 1）；只剩 needs_review → **INCONCLUSIVE**（退出码 3）；否则 **PASS**（退出码 0）。`--diagnostic` 只展示、退出码恒为 0。

**family 是独立单位**：同一 family 的臂、轮次、重复、checkpoint 都是嵌套观测；率按 family 计，配对比较用 family 级符号检验（与锚点密度的合并泊松检验是同一个精确条件二项检验的特例，实现只有 `idiolect/evals/stats.py` 一份）。family 数不足时 PASS 只表示「未检出违规」。

**标签**：`labels/v1` 的人工（盲评）标签只能改写 `needs_review`，并标注 `human:<标注者>[:blind]`；模型 judge 记录在 `judge` 字段，必须写明 judge 模型与生成模型的关系，只作为辅助证据显示，**不改**任何判定。

## 7. 能力与四种模式

`idiolect capabilities` 列出每个能力的版本、输入合同、适用任务、scorer、fixture、依赖、覆盖与不覆盖：

| 能力 | 默认 | 说明 |
|---|---|---|
| `style` | 启用 | 字数硬上限（与 style_target 块同一个数）、仓库 tools 在场时的句数上限 / 越界高危 / canon 事实 / 泄漏 |
| `spatiotemporal` | 显式 | 本章的证据合同与 grounding 任务 |
| `long-context-stress` | 显式 | 见 [`10-long-context-stress.md`](10-long-context-stress.md) |

任务声明自己需要的能力；没全部启用时整条 grounding 链 `not_applicable` 并写明原因，证据块不会进 prompt；启用了却缺必要合同或样本时报 `missing`，不降级成通过。四种模式的命令见 README 与第 05 篇。

## 8. 实验登记、manifest 与可比性

`idiolect eval` 默认把 `results.json` / `responses.json` / `manifest.json` 登记到 `report/experiments/<实验 ID>/`（`IDIOLECT_REPORT_DIR` 可改），并更新 `index.json`。manifest 记录：

- 代码：git revision、是否 dirty、工作区 diff 指纹、包源码指纹（装成 wheel 时写明没有 git 元数据）；
- 输入：suite 与生成来源、回复集、标签、adapter、能力及版本、装配参数指纹、逐任务 messages 指纹；
- 生成：runner 类型、模型、temperature、输出预算、是否付费、是否合成；
- scorer：grounding / matcher 版本、本次实际可用的风格检查、clean 口径、评分源码指纹；
- 时钟、脱敏规则、哪些可精确重放、哪些不公开；**密钥与 base_url 从不写入**。

可比性（`compare_manifests` / `idiolect compare`）：两份 manifest 必须声明**同一组**预注册干预变量；声明内的字段可以不同，声明外的字段不同 → `blocked`（阻止池化与改善判定）；必需字段缺失 → `incomparable`；任一侧是干跑 → `blocked`。比较结果逐字段列出原因。只有 `comparable` 时才给「改善 / 退化 / 无显著变化 / 功效不足」的判断，否则判断是 `refused`。

登记目录读取时逐一复核产物指纹：被改过、过期、混臂一律 fail closed。探针批次（`probe_runner`）的 metadata 从 v2 起也带 `code` 与 `intervention`，`report_html.py` 按同样的规则判两批可比性；旧批次只能浏览。

## 9. 同链变异自测与健康反控制

`idiolect selftest` 跑 25 个变异体与 9 组健康反控制。每个变异体只在一个注入点改一处，然后走与真实评测**相同**的 `evaluate_suite`（比较类走 manifest / 登记），报告写明在哪个阶段被抓到：

| 注入点 | 变异体（示例） |
|---|---|
| 输入合同 | 历史提升为当前（已过期）、隐藏值写进可见输入、悬空更正引用、条目缺 status |
| adapter | 历史被静默提升为当前、不可见真值进可见包、证据 ID 互换、历史桶被丢弃 |
| 渲染 / 装配 | provenance 全量照抄、评估字段被序列化进 messages、预算尾裁丢掉关键证据 |
| 回复 | 伪造证据 ID、错误前提被接受、未知被肯定、未知被否定 |
| 评分器 / 聚合 | 空回复判通过、漏写 applicability、吞掉隐藏参数的空洞门禁 |
| 回复集 / manifest | 干跑冒充实测、回复集属于旧版 suite、生成时 prompt 不同、混批、评分器或模型变化未声明 |
| 等价体 | 包一层 wrapper、kwargs 透传、参数改名（行为不变，**必须不被判差异**） |

健康反控制：第三人称否定、合法的不知道、不要求引用的任务里顺手带了引用、同名不同场景、全角数字与省略号、换一种时间限定、换一种纠正说法、五人短句与语气差异——全部必须保持 PASS。

每次 `eval` 还自带两类有效性自检：**门禁金丝雀**（已知隐藏值、私有路径、已知违规必须让检查器翻转判决）与**表示算子认证**（认证范围内的算子必须保持判决）。任一失败，这次运行 FAIL。

> 变异体被抓到只说明「这类注入缺陷能被这条链检出」，不是自然缺陷的检出率，更不是模型能力提升。存活的变异体与残余盲区原样列在自测报告里。

## 10. inspect 报告与付费 runner

`idiolect eval … --html`、`idiolect report <实验目录…>`、`idiolect compare … --html` 生成离线 HTML：逐任务看模型可见 messages、raw / clean、评估侧期望（黄色边线标注，从未进 messages）、逐层判定与分母、装配 trace、长上下文计量、变异自测与比较拒绝原因。页面只展示已落盘的判定，不重算；数据以转义后的 JSON 嵌入，脚本只用 `textContent` 写入。

付费 runner 必须显式 `--yes` 并设 `--max-calls`；运行前打印调用量、输入字符数，token 与费用只有给了单价 / 字符比例时才粗估（并标明不是 tokenizer 计数）。`--dry-run` 只写占位记录，评分时一律 missing。

## 11. 方法学来源与边界

本章的组织方式吸收了一项观察者证据合同研究的第一部分（无模型回放与门禁审计）中的几条做法：

- **把全局真值、观察者证据、模型投影与评估侧 Oracle 分开**。这里对应可见合同（模型侧）与任务的 `expect` / `oracle`（评估侧）的硬分界，以及边界检查对最终 messages 的扫描；
- **门禁的通过必须可被故障注入推翻**。被比较的 artifact 必须真的经过被测链路；旁路参照实现的敏感性不能替代被测链的检出力——对应同链变异体与每次运行的金丝雀；
- **良性表示变换要逐算子认证**，不能凭「字符串规范化直觉」推定——对应 `certify_operators()` 的成对探针；
- **独立单位是 family**，嵌套观测不当独立样本（避免伪重复）；功效不足时明说无结论；
- **描述性数字与可推断结论分开**：合成回放、干跑、单批次运行统计只能描述链路，不能写成模型效果。

本章实现的是协议层与评测层；它不证明任何模型「理解时间」，也不宣称新的非干扰算法。

---

**上一站**：[`08-context-workspace.md`](08-context-workspace.md) ｜ **下一站**：[`10-long-context-stress.md`](10-long-context-stress.md) ｜ **索引**：[`README.md`](README.md)
