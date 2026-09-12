---
name: idiolect-evaluate
description: "Run and read idiolect's evaluation loop on your own cast: build fixtures, dry-run the probe, run a real probe against an OpenAI-compatible endpoint, score with the four-step report, pool multiple arms, estimate power, and leave before/after prompt evidence. Use this skill whenever the user asks to prove a prompt change made replies more in character, wants to run the probe or probe_report, asks what fidelity or the scene fit score mean, wonders whether a score difference is real, or needs the gates that must pass before claiming an improvement. Covers the mock clock, the n=6-per-cell rule, pooling, the verbatim-copy audit, and the mechanical plus prompt-diff gates."
---

# idiolect-evaluate：跑评测，并且知道什么时候不能下结论

这套评测存在的唯一理由是：**「像不像」要变成可以测量、可以复现、可以否证的量**。

前置：角色包可跑（[`idiolect-cast`](../idiolect-cast/SKILL.md)）。方法学细节见 [`docs/04-evaluation.md`](../../../docs/04-evaluation.md)。

## 1. 时钟先钉住

角色对时段敏感（凌晨和下午的回复不一样），所以评测统一跑在固定的假白天：

```bash
py -X utf8 tools/mock_clock.py                                  # 看当前生效时间与来源
py -X utf8 tools/mock_clock.py --set 2026-09-12T15:00:00+09:00  # 打印要设的环境变量行
```

那条命令只**打印**环境变量（子进程改不了父 shell），贴进 shell 才生效。真实时钟下跑出的数字不能与 mock 批次比较。

## 2. 夹具 → 干跑 → 真跑

```bash
py -X utf8 tools/probe/make_fixtures.py                                   # 生成占位夹具（system 段为空）
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run \
    --assemble --registry --runs 1                                        # 不调 LLM，只验证夹具与装配
py -X utf8 tools/probe/probe_runner.py --label run1 \
    --assemble --turn-logic --registry --cats 通用场景 --runs 3           # 真跑（要 LLM_* 三个环境变量）
```

**`--assemble` 不能省**：仓库自带的夹具 system 是空的，不加它测到的是「没有任何角色 prompt 的裸模型」。

想要自己的夹具，就把真实运行时的 messages dump 放进 `fixtures/`（只换最后一条 user 内容）——来源顺序是 `fixtures/` 里最新的 `messages_<char>*.json`，再退到 `_offline_smoke_out/`。

## 3. 打分：四步 + 可选池化

```bash
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
py -X utf8 tools/score/probe_report.py --off-labels run1 --on-labels run2   # 加两个臂才跑池化
```

四个指标必须**一起**看，少看一个就会得出错误结论：

| 指标 | 看什么 | 误读方式 |
|---|---|---|
| `scene_distill` | 回复长度/句数与「同角色同场景原作分布」的贴合度 | 当绝对分用——它是相对量 |
| `_repeat_rate` | 同一格多次回复是否互不重样 | 忽略它，把复读当成「稳定」 |
| `_copy_audit` | 是否逐字照抄了注入正文里的句子 | 只看分数不看复述率 |
| `scene_feedback` | 原作句与模型句并排 | 不看回复就下结论 |

**单臂每格 6 条不下结论**：同一场景同一 prompt，贴合分能从 0.551 摆到 0.350，比要测的效应还大。要下结论就池化多臂（多个夹具/批次的同向变化），并用功效估算看样本量够不够：

```bash
py -X utf8 tools/score/_pool_arms.py --off-labels … --on-labels …
py -X utf8 tools/score/power_calc.py
```

## 4. 门禁（不过就别提交）

```bash
py -X utf8 tools/offline_smoke.py                      # 零写零 LLM 的总闸（含单测）
py -X utf8 tools/gates/voice_meta_gate.py              # 元叙述
py -X utf8 tools/gates/_gen_scene_check.py             # 通用场景正文
py -X utf8 tools/gates/_tl_deep_check.py               # 深模块
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase before
#   …改 prompt…
py -X utf8 tools/gates/dump_prompt.py --all --matrix --phase after
```

prompt diff 门禁逐项确认：层顺序、块边界、触发范围、**无关场景零漂移**、预算、当前 user 与回复目标的位置。`--phase before` 是「深模块/通用场景开关全关」的 A/B 臂，不是改动前快照——比改动前后请用同一 phase。

## 5. 什么时候该说「没有结论」

- 每格样本 < 6 条，或只跑了一个臂 → 只能当线索。
- 换了模型 / 夹具 / 时钟 → 跨批次不可比。
- 分数涨了但回复更难读 → **读至少 6 条回复并和原作同场景并排看**，分数只负责筛嫌疑。
- 「长度偏差」只用来找嫌疑人：灯的输出比参照长 5 倍，一半原因是她的省略号也计字数。

---

相关：[`docs/04-evaluation.md`](../../../docs/04-evaluation.md)（指标口径与常见误读）｜[`docs/06-lessons.md`](../../../docs/06-lessons.md) 的 C 组（评测方法踩过的坑）
