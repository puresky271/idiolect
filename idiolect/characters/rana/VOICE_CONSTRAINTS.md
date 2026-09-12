# rana — 要乐奈语气约束 SSOT 索引

> 当前可编辑 SSOT：`rana/voice.py:VOICE_MANIFEST`
> 兼容映射：`turn_agents.prompt_cards._PERSONA_FINGERPRINT["乐奈"]`

`VOICE_MANIFEST` 集中拥有乐奈的极短句、跳题、兴趣信号、关系差异、知识问答和反模板化约束。QA、称呼和回复结构约束也由同一 `voice.py` 导出。

长 canon 由 `rana/canon.py:PROFILE_TEXT` 拥有；关系状态、记忆和当前事实属于各自运行时层，不应复制进语气 manifest。

`rana/turn_logic/` 是**已启用**的动态 block 层（2026-09-12 起 = 3 个场景 + 4 个深模块）：

| 文件 | 内容 | 关闭开关 |
|---|---|---|
| `scenes.py` | 吉他/演出、抹茶/食物、猫/观察（场景层：给分寸） | `RANA_TURN_LOGIC_ENABLED=0`（整层） |
| `space.py` | 外婆 / SPACE / 容身之处（深模块；含「外婆来听演出」override） | `RANA_TURN_LOGIC_SPACE_ENABLED=0` |
| `nap.py` | 困 / 午睡 / 找地方睡（深模块） | `RANA_TURN_LOGIC_NAP_ENABLED=0` |
| `interesting.py` | 「有趣」标尺（深模块；含「有趣的女人」旧说法 override） | `RANA_TURN_LOGIC_INTERESTING_ENABLED=0` |
| `cat_talk.py` | 猫 / 能听懂猫说话（深模块；命中时压制场景层 `rana_cat`） | `RANA_TURN_LOGIC_CAT_TALK_ENABLED=0` |

约束：

- 轮次预算 = 深模块 ≤1 块 + 场景 ≤1 块 + 通用场景 ≤1 块（最多 3 块）。
- 触发词必须有语料实证；正文不许出现语料/统计类元叙述（角色会读到它）。
  两条都由 `test_soyo_rana_deep_turn_logic.py` 守着。
- 任何新增/修改都要跑 `_audit_scratch/v41/bench/dump_turn_logic_gate.py --phase before|after` 做 prompt diff。
  **不要**用 `scripts/dump_live_chat_prompt.py`：那条路径是 `dev_mode=True`，
  而 turn_logic 按设计在开发者模式不触发，dump 里根本看不到这一层（只能证明其余 prompt 零漂移）。
