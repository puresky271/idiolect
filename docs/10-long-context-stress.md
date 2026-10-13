# 长上下文压力：可选能力 `long-context-stress`

> 讲什么：长上下文压力测试的预注册 family 设计、确定性生成器、上下文计量与配对分析。 ｜ 前置：[`09-evidence-grounding.md`](09-evidence-grounding.md)；配套代码 `idiolect/evals/longctx.py`，内置计划 `idiolect/benchmarks/long-context-smoke.plan.json`。

**目录**：[1 它测什么、不测什么](#1-它测什么不测什么) ｜ [2 预注册计划](#2-预注册计划-long-context-planv1) ｜ [3 生成器](#3-确定性生成器) ｜ [4 计量](#4-计量字符字节token) ｜ [5 配对分析](#5-family-配对分析) ｜ [6 对照与回放](#6-对照合成回放与真实模型) ｜ [7 命令](#7-命令)

## 1. 它测什么、不测什么

测的是：**同一个语义任务**在上下文变长、关键证据换位置、干扰变多、历史与当前冲突、多轮累积、预算尾裁、执行包位置变化时，**装配是否还保住了证据**、**回答是否还被证据约束住**。

不测的是记忆系统。长输入本身不等于记忆能力；这里不引入任何记忆存储，不检索生产历史，不读真实角色记忆或密钥。宿主的真实上下文只能通过[显式快照 adapter](09-evidence-grounding.md#3-显式快照-adapter) 作为可选输入进来。

能力默认关闭。不启用时，相应任务的 grounding 轴显示 `not_applicable`，默认的语言工作流不受影响。

## 2. 预注册计划 `long-context-plan/v1`

```json
{
  "schema_version": "long-context-plan/v1",
  "plan_id": "long-context-smoke", "plan_version": "1.0.0", "seed": 20261014,
  "preregistration": {"unit": "family", "min_families_for_claims": 8,
                      "primary_contrast": "length=long 下 position=middle 对比对照臂（short/head）"},
  "families": [
    {"family_id": "lcf-lenpos-01", "design": "length_x_position",
     "factors": {"length": {"short": 600, "long": 6000}, "position": ["head", "middle", "tail"]},
     "control": {"length": "short", "position": "head"}, "intervention": ["length", "position"],
     "semantic": {"user": "actor_b 现在在哪里？", "key": {"evidence_id": "evidence_17", "text": "…"},
                  "expect": {"policy": "answer_current", "required_claims": ["…"]}}}
  ]
}
```

每个 family 固定**一个**语义任务与独立的期望标签，只在 `intervention` 声明的因子上变化；`control` 指定对照臂。会改变时间或权限语义的变化（例如把关键证据从当前挪到历史）必须**另开 family**，不能假装只改了长度。

| 设计 | 因子 | 说明 |
|---|---|---|
| `length_x_position` | 总长度 × 关键证据位置（首/中/尾），干扰密度 | 干扰项是其他 actor 在其他地点的观察 |
| `multiturn_conflict` | 有无历史/当前冲突 × 轮数（短/长） | 早先轮次说过旧值；证据里旧值在历史、新值在当前。需要两项能力 |
| `controls` | 预算（充足/截断） | 截断臂的证据层被整块尾裁；期望改为不编造，装配缺失单独记账 |

执行包位置与输出预算作为记录项进入计量与 manifest；输出预算只在真实模型 runner 下有意义。

## 3. 确定性生成器

`generate_suite(plan)` 把计划展开成 `benchmark-suite/v1`，每个臂一个任务（`task_id = <family>::<因子=水平,…>`）：

- 种子由 `plan.seed + family_id + 用途` 的 SHA-256 派生，不依赖 Python 的随机化哈希，跨进程、跨平台可复现；
- 干扰项生成时**断言**不含任何期望主张或禁止主张的写法；
- 计划的 SHA-256、生成器名与版本写进 suite 的 `generated_from`，再进实验 manifest。

## 4. 计量：字符、字节、token

`measure()` 只读最终 messages 与装配 trace，不重算装配：

| 字段 | 含义 |
|---|---|
| `total_chars` / `total_bytes_utf8` | 精确计量 |
| `chars_by_role`、`layers` | 按角色、按工作区层的字数；每层是否 pinned、是否保留 |
| `trimmed_layers`、`max_chars` | 被预算摘除的层与预算 |
| `history_messages` | 实际进入 messages 的历史条数（多轮 trace 记录真实累计上下文） |
| `evidence_items`、`key_position_index`、`key_position_fraction` | 证据条数与关键证据在可见包里的位置；不在 messages 里时为空 |
| `execution_packet_index` | 执行包贴在哪条消息上 |
| `tokens`、`tokenizer` | 只有接入 tokenizer（记录名称与版本）时才有；否则 `null` / `unknown`，**字符数不冒充 token** |

## 5. family 配对分析

`paired_families(results)` 在 family 内把每个非对照臂与对照臂比较 grounding 判定：`degraded`（对照通过、该臂失败）、`improved`、`same`、`undecided`；再按因子水平汇总。主对比用 family 级符号检验（第 09 篇第 6 节同一个实现）。

报告分清四件事：装配丢了证据（prompt 边界 fail，计量里关键证据不在 messages）、模型没用证据（回复 fail）、scorer 不适用或判不了（`not_applicable` / `needs_review`）、缺测（`missing` / `empty` / `error`）。token 数、重复 filler、轮数、checkpoint 都不当独立样本。

内置计划只有 4 个 family，低于预注册下限 8：它验证链路与计量，**不支持**任何「模型在长上下文里更好/更差」的结论，报告会照实写「结论强度不足」。

## 6. 对照、合成回放与真实模型

| 回放 | 期望门禁 | 用途 |
|---|---|---|
| `long-context-smoke.healthy` | PASS | 健康保留关键事实、合法的历史限定、截断臂合法地说不知道 |
| `long-context-smoke.lost_middle` | FAIL | 长上下文且关键证据在中段的臂答「不知道」：配对分析应只在这些臂上报 degraded |
| `long-context-smoke.failure_controls` | FAIL | 对照臂给空回复 / 报错：空与报错不能通过 |

这些回放由期望**生成**，只测 harness。模型对长上下文的真实反应只能用显式付费 runner 测：先 `idiolect run --dry-run` 看调用量估算，再 `--yes --max-calls N`。不会自动开始大批量或跨模型压测。

## 7. 命令

```bash
python -m idiolect bench inspect long-context-smoke                         # 任务、因子、期望
python -m idiolect bench inspect long-context-smoke --meter --capabilities long-context-stress,spatiotemporal
python -m idiolect eval --suite long-context-smoke --responses builtin:long-context-smoke.healthy \
    --capabilities long-context-stress --html                               # 单独长上下文
python -m idiolect eval --suite long-context-smoke --responses builtin:long-context-smoke.lost_middle \
    --capabilities long-context-stress,spatiotemporal --html                # 联合能力 + 负对照
```

`--html` 生成的 inspect 页里有计量表与 family 配对结果。

---

**上一站**：[`09-evidence-grounding.md`](09-evidence-grounding.md) ｜ **下一站**：[`11-upgrade-guide.md`](11-upgrade-guide.md) ｜ **索引**：[`README.md`](README.md)
