# rana — 要乐奈专属逻辑进度跟踪

> 包路径：`D:/python/mygo_chat/rana/`
> 建档：2026-09-12（此前无本文件——素世 / 乐奈是五包里缺的两个，同日补齐）
> 当前状态：**已接入主流程**（voice_check 在 chat_server 有调用点；
> turn_logic 经 `character_role_packages.render_turn_special_block` → `mygo.py` 的
> `lyrics_context` slot）

---

## 0 · 设计原则（拍板项、不要轻动）

1. **称呼口径**：叫立希「**Rikki**」（她语料里「立希」0 次 / Rikki 8 次，jp りっきー 10）；
   对其他人用裸本名，不加「小」。例外见 `GrandmaWordingTests`：外婆统一写「外婆」
   （语料「奶奶」3 / 「外婆」2 是译名不统一，项目口径取「外婆」）。
2. **极简是默认，不是全部**：金标准中位 6 字、≤6 字占 57%。turn_logic 的作用**不是**让她变话多，
   而是在**正确的场景给出正确的具体物**——避免她把极简退化成空泛表态（「嗯。」「不知道。」）。
   「不知道」在乐奈语料里 0 次（`TIC_FORBIDDEN`）。
3. **和猫是同类、不是宠物**：能听懂猫语、可以转述猫的话、可以请猫帮忙。
   陈述这件事像陈述天气，不解释、不自我调侃、不卖萌。
4. **「有趣」是评价系统本身**，不是口头禅。canon 经典台词三句并列、**各有锚点，不是对错关系**：
   - 「有趣的女人。」= 她**最早的说法**（第一次评价灯时就是这句）+ 给**爱音**的最高评价（固定说法）
   - 「有趣的女孩子。」= 被凛凛子改口之后的**通用形式**
   - 「无聊的女孩子。」= **失望时**（她说过一次，那次她离开了乐队）
   出处是外婆评价母亲的那句「有趣的女人」。
   ⚠️ 别再犯 2026-09-12 那个错：不能因为「凛凛子纠正过女人→女孩子」就删掉「女人」形态，
   那是 canon 的具名锚点（【对爱音】整段标题就是「有趣的女人 / 不需要 / 但接受温热的风」）。
5. **诊断与 prompt 分工**：prompt 让模型不写（manifest 硬约束 + turn_logic 分寸），
   `voice_check` 兜住漏网的；`clean_reply` 只做**无损**变换，其余只告警。
6. **风格改写单独走 API 层**：起手确认消减（`voice_check/opener.strip_redundant_ack`）
   **会删字**，所以不放进 `clean_reply`，由 `rana.api.post_reply_voice_check` 单独调用。
   依据：原作名词起手 55% / 语气词 8%，而生产是 19% / 67%；
   prompt 侧两次 A/B 均不显著（+2.04pp，z=0.30），故改后处理。
   短确认（「嗯。开心」）与疑问起手（「嗯？」）都不动；`RANA_VOICE_CHECK_ACK_STRIP=0` 可关。

---

## 1 · 待办子系统（按优先级排序）

### P0 · 已识别、值得专门做

- **短确认起手率**（`嗯。` / `嗯？`）：后处理已把**冗余**的那种删掉
  （名词起手 19% → 43%，原作 55%），但剩下的 33% 是「嗯。＋1~3 字」这种**短确认形态**，
  在语料里占她起手行的 38%（属于签名，不能删）。
  要再往下压只能动生成侧，而 prompt 侧 A/B 两次都不显著 —— **先按功效算样本量再说**。

### P1 · 中期推进

- **`rana_food` 的品类词**：语料支撑只有「抹茶冰淇淋 4（全是她）」+ 一组她独有的抹茶搭配（各 1），
  「抹茶芭菲」在她语料里只 1 次。要不要把品类收窄到「抹茶 + 冰淇淋」需要一次**有功效的**探针判断。
- **`interesting` 与通用 `affection` 的交互**：被示好时她既不给情感回应（`affection` 模块）
  又可能给「有趣」评价（`interesting` 模块）——两者同时命中时的优先级目前靠轮次预算挡，
  没有专门的语义判别。

### P2 · 看后续需要

- **time-driven 睡眠**：`nap.py` 目前是 text-driven（没有 睡/困 线索就不猜她困）。
  要做成「深夜/清晨自动困」需要接 `now_jst` + `ledger`，并配 time-driven 的 dump 门禁。
- **手艺部 / 智能手机**（canon 里她是吉祥物般的存在、几百条未读、第一条消息是打错的
  「扌末茶芭菲」）：语料覆盖薄，暂由 canon 支撑。

---

## 2 · 当前包结构（现状）

```
rana/
├── __init__.py
├── api.py                  is_rana / render_supplemental_blocks / postprocess_reply
├── canon.py                PROFILE_TEXT（角色长档案 SSOT）
├── voice.py                VOICE_MANIFEST + REPLY_STRUCTURE_CONSTRAINTS + NICKNAME_RULE …
├── VOICE_CONSTRAINTS.md
├── voice_check/            2026-09-12 模块化（此前是单文件）
│   ├── __init__.py         公开 API：clean_reply / inspect（**只做无损变换**）
│   ├── thresholds.py       语料实测阈值 + 正则 + 口癖禁词表
│   ├── punctuation.py      无损清洗：感叹号配额 / 省略号归一
│   ├── opener.py           风格改写：冗余起手确认消减（**会删字**，只在 API 层调用）
│   └── tone.py             诊断：角色阈值 + 助手腔（结构级检测器）
└── turn_logic/
    ├── __init__.py         窄入口 build_rana_special_block + 深模块预算/压制表
    ├── scenes.py           吉他/演出、抹茶/食物、猫/观察（场景层，SceneModule）
    ├── space.py            外婆 / SPACE / 容身之处（深模块）
    ├── nap.py              困 / 午睡 / 找地方睡（深模块）
    ├── interesting.py      「有趣」标尺（深模块）
    └── cat_talk.py         猫 / 能听懂猫说话（深模块）
```

---

## 3 · 下一步（接下来要做的）

- 用**真实 chat_sessions 历史**核对 `interesting` 是否把「有趣的女孩子」用得太频繁
  （探针夹具重复生成会放大，不能作数）。
- 深模块的真实探针口径：`probe_runner --registry --cats 深模块 --turn-logic`，
  收尾用**唯一入口** `probe_report.py`（打分 + 并排 + 重复度 + 复述审计 + 池化）。
- 方法学与踩坑清单见 `docs/brain/character/prompt_distillation_evaluation.md`；
  未验证项与 backlog 见 `_audit_scratch/v41/bench/REPORT_backlog_and_handoff.md`。

---

## 4 · 修订日志

- **2026-09-12（第 7 轮）** 非 prompt 手段落地：`voice_check/opener.py` 的
  `strip_redundant_ack`（内容足够长时删掉冗余的「嗯。」起手）。名词起手 19% → 43%
  （原作 55%），对原作语料近乎 no-op（改动 4%、名词率不降）。
  接线在 `api.post_reply_voice_check`，**不在** `clean_reply`（后者契约是无损）。
- **2026-09-12（第 6 轮）** 注入正文**零例句**改造：正文里凡能整句搬运的内容都会被照抄
  （实测生产臂 22~27% 的回复逐字复述）；现在只给字数上限 + 句数 + 结构描述 + 口癖起手。
- **2026-09-12** canon 口径修正（**一次自我误判的回滚**）：曾据「凛凛子纠正过女人→女孩子」
  把 `voice.py` 里爱音那行改成「有趣的女孩子」——读 `canon.py` 后发现【对爱音】整段标题就是
  「有趣的女人 / 不需要 / 但接受温热的风」、正文写明那是**给过的最高评价**。已回滚，
  并把 canon 的三句经典台词（女人=首次评价灯时／女孩子=改口后／无聊的女孩子=失望时）
  补进 `voice.py`【口癖】（此前 SSOT 只有爱音那一句，另两句缺失）。
  `nap.py` 的睡处同步改用 canon 原话（暖炉边 / 学校长凳 / 屋顶 / 树上，不另编场所）。
- **2026-09-12** 建档；turn_logic 从 1 个 `scenes.py` 扩成「3 场景 + 4 深模块」；
  深模块带 3 层渐进激活 + per-session 去重 + canon override；
  `cat_talk` 命中时压制场景层 `rana_cat`（同一话题不写两块）。
- **2026-09-12** `voice_check` 从单文件拆成 4 个模块（对齐 tomori/taki/anon 形态）；
  检测器四类误报修复后同步。
- **2026-09-12** 称呼更正：立希 → Rikki（原 PROFILE_TEXT 写「直呼立希」与语料相反）；
  外婆口径从「奶奶」改回「外婆」。
- **2026-09-12** 词表落地：`voice.py` 加【口癖】【常用物件与话题】【句式结构】。
