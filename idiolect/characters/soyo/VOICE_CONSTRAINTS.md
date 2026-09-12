# soyo — 长崎素世语气约束 SSOT 索引

> 当前可编辑 SSOT：`soyo/voice.py:VOICE_MANIFEST`
> 兼容映射：`turn_agents.prompt_cards._PERSONA_FINGERPRINT["素世"]`

`VOICE_MANIFEST` 集中拥有素世的外人/MyGO 状态切换、间接关心、冷刺、旧事触发、关系差异、知识问答、失败表达和反模板化约束。QA、称呼和回复结构约束也由同一 `voice.py` 导出。

长 canon 由 `soyo/canon.py:PROFILE_TEXT` 拥有；关系状态、记忆和当前事实属于各自运行时层，不应复制进语气 manifest。

`soyo/turn_logic/` 是**已启用**的动态 block 层（2026-09-12 起 = 3 个场景 + 2 个深模块）：

| 文件 | 内容 | 关闭开关 |
|---|---|---|
| `scenes.py` | 观察/点破、红茶/待客、旧事触发（场景层：给分寸） | `SOYO_TURN_LOGIC_ENABLED=0`（整层） |
| `home.py` | 家 / 妈妈 / 家务（深模块，3 层渐进） | `SOYO_TURN_LOGIC_HOME_ENABLED=0` |
| `wind_ensemble.py` | 吹奏乐社 / 低音大提琴（深模块；含「为什么换成贝斯」override） | `SOYO_TURN_LOGIC_WIND_ENSEMBLE_ENABLED=0` |

约束：

- 轮次预算 = 深模块 ≤1 块 + 场景 ≤1 块 + 通用场景 ≤1 块（最多 3 块）。
- 触发词必须有语料实证；正文不许出现语料/统计类元叙述（角色会读到它）。
  两条都由 `test_soyo_rana_deep_turn_logic.py` 守着。
- 乐器译名口径：对外说「**低音大提琴**」（语料原词），canon 的「低音提琴」是同义变体；
  **不是**大提琴 / 小提琴。`home.py` 也不许把家世写成倾诉。
- 任何新增/修改都要跑 `_audit_scratch/v41/bench/dump_turn_logic_gate.py --phase before|after` 做 prompt diff。
  **不要**用 `scripts/dump_live_chat_prompt.py`：那条路径是 `dev_mode=True`，
  而 turn_logic 按设计在开发者模式不触发，dump 里根本看不到这一层（只能证明其余 prompt 零漂移）。
