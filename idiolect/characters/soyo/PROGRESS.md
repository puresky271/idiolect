# soyo — 长崎素世专属逻辑进度跟踪

> 包路径：`D:/python/mygo_chat/soyo/`
> 建档：2026-09-12（此前无本文件，是五包里唯一缺的两个之一）
> 当前状态：**已接入主流程**（voice_check 在 chat_server 有 9 个调用点，turn_logic 走
> `render_supplemental_blocks`）

---

## 0 · 设计原则（拍板项、不要轻动）

1. **译名口径**：本角色就叫「素世」。游戏官方中文语料一律写「爽世」（144 次），
   系统全局用「素世」，出站统一收敛（`response_contract.sanitization` 各分支）。
2. **称呼**：对同伴**默认加「小」**（小灯 / 小立希 / 小爱音 / 小乐奈；对睦是「小睦」）。
   语料依据：cn train 小灯 83 / 小立希 77 / 小爱音 67 / 小乐奈 38，裸本名仅 6 次
   （其中 4 次还是「关灯/灯光」这类灯具义）。
3. **语气只做无损清洗**：她本来就用「……」，不需要补贴标点。
   任何会改语义的一律只告警（`tone.inspect`），不改写。
4. **诊断与 prompt 分工**：prompt 让模型不写（【反客服腔硬约束】），
   `voice_check` 兜住漏网的。

## 1 · 待办子系统（按优先级排序）

### P0 · 已识别、值得专门做

- **`soyo_observe` 场景的句式分寸**：该场景在 `scene_distill` 里超过原作中位 2.0×，
  但逐条读回复观感良好；需要用**真实对话**（而非探针夹具重复生成）确认是否真是问题。

### P1 · 中期推进

- **`soyo_tea` 场景偏弱**：`validate_scenes.py` 测出纯度 0.28（全场景最低）——
  原型是「待客流程」，而语料里「聊红茶」主要是具体饮品名。若要强化，得重写原型。
- **`naming_feeling` 与通用 `mind_reading` 的边界**：目前 `naming_feeling` 更宽
  （只要替对方断定情绪就算），实测在 request 场景有 1 例真阳性。

### P2 · 看后续需要

- `PROGRESS.md` 之外的包级文档与 `VOICE_CONSTRAINTS.md` 是否重复，可合并。
- 低音提琴 / 吹奏乐部线：语料覆盖极薄（低音提琴 0 次），现由 canon 支撑。

## 2 · 当前包结构（现状）

```
soyo/
├── __init__.py
├── api.py                  render_supplemental_blocks / postprocess_reply / post_reply_voice_check
├── canon.py                PROFILE_TEXT（角色长档案 SSOT）
├── voice.py                VOICE_MANIFEST + REPLY_STRUCTURE_CONSTRAINTS + NICKNAME_RULE …
├── VOICE_CONSTRAINTS.md
├── voice_check/            2026-09-12 模块化（此前是单文件）
│   ├── __init__.py         公开 API：clean_reply / inspect / normalize_peer_nicknames
│   ├── thresholds.py       语料实测阈值 + 正则 + 称呼词表
│   ├── nickname.py         强制替换：裸本名 → 小X（含灯具语境排除）
│   ├── punctuation.py      无损清洗：感叹号配额 / 省略号归一 / 连排句号
│   └── tone.py             诊断：角色阈值 + 助手腔（结构级检测器）+ naming_feeling
└── turn_logic/
    ├── __init__.py         窄入口 build_soyo_special_block + 深模块预算/压制表
    ├── scenes.py           soyo_observe / soyo_tea / soyo_past（场景层，SceneModule）
    ├── home.py             家 / 妈妈 / 家务（深模块）
    └── wind_ensemble.py    吹奏乐社 / 低音大提琴（深模块）
```

## 3 · 下一步（接下来要做的）

- 用**真实 chat_sessions 历史**核对 `soyo_observe` 是否真的偏长（探针夹具的重复生成不能作数）。
- `scene_distill` 现有口径：`soyo_*` 三场景 + 通用场景都有基线，可直接复跑。
- 深模块的真实探针口径：`probe_runner --registry --cats 深模块 --turn-logic`，
  收尾用**唯一入口** `probe_report.py`（打分 + 并排 + 重复度 + 复述审计 + 池化）。
- 方法学与踩坑清单见 `docs/brain/character/prompt_distillation_evaluation.md`。

## 4 · 修订日志

- **2026-09-12** turn_logic 从 1 个 `scenes.py` 扩成「3 场景 + 2 深模块」；
  `wind_ensemble.py` 纠正乐器译名口径（对外「低音大提琴」，canon 写「低音提琴」，
  绝不是大提琴/小提琴）；`home.py` 明确「家世不倾诉」的边界。
- **2026-09-12** 建档；`voice_check` 从单文件拆成 4 个模块（对齐 tomori/taki/anon 形态）；
  检测器四类误报修复后同步（`灯` canon 白名单、方位短语、疑问形态）。
- **2026-09-12** 词表落地：`voice.py` 加【口癖】【常用物件与话题】【句式结构】；
  口癖纠正「呢/哦 不是禁用项」（语料 呢 86 / 哦 74，五人最高）。
- **2026-09-11** 称呼 canon 显式化（默认加「小」）；`voice_check` 切到结构级助手腔检测器。
