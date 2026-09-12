# taki — 椎名立希专属逻辑进度跟踪

> 包路径：`D:/python/mygo_chat/taki/`
> 启动日期：2026-05-11
> 当前状态：**骨架建立、未接入主流程**

---

## 0 · 设计原则（拍板项、不要轻动）

1. **立希专属逻辑独立成包、不污染通用基建**
   - mygo.py / character_profiles.py / pet_prompt_registry.py 保持通用
   - 凡是「只对立希有意义」的逻辑（鼓 / DTM / Afterglow 狂热粉 / 姐姐劣等感 / 称呼规则）都搬到 taki
2. **接入主流程通过窄接口**
   - `taki.api` 暴露 `is_taki` / `render_supplemental_blocks` / `post_reply_voice_check`
   - 内部子模块（turn_logic / voice_check）caller 不直接 import
3. **不微调模型、不增 LLM 调用**
   - 全部在 prompt 层和后处理层做
   - 红线：character_profiles.py 仍然是 SSOT、taki 不能覆写已确定的角色 canon
4. **可关闭、可灰度**
   - 任意 taki 子系统加 env flag、出问题秒关回退到通用路径
5. **测试先于上线**
   - 每个子系统配 1-3 个 offline harness、能跑 deterministic 验证

---

## 1 · 待办子系统（按优先级排序）

### P0 · 已识别、值得专门做

#### 1.1 visual_claim_detect（视觉幻觉检测）
- **canon 来源**：VOICE_CONSTRAINTS §1.6【立希·硬约束 P0】
- **当前缺失**：纯文字交流场景下、LLM 仍偶尔吐 "你穿这个挺好看的" / "你今天看起来累" 这种 visual claim
- **目标**：post-reply scan、命中 `^你(穿|戴|长得|脸|身高|发型|看起来)` 等 pattern 即 flag
- **接入点**：`taki.api.post_reply_voice_check` → 写日志、严重时（P0）触发 rewrite
- **状态**：未开始

#### 1.2 soft_tone_throttle（语气向温柔漂移检测）
- **canon 来源**：VOICE_CONSTRAINTS §1.1【底层标签】反例
- **当前缺失**：mygo softness guard 词库窄、只抓「好开心 / 好喜欢 / 真的很」等少数词、漏掉「慢慢来 / 不用担心 / 没关系的 / 加油哦」等爱音/素世风
- **目标**：
  - 扩词库到 30+ 个温柔正面 marker
  - 跨轮统计：连续 2 轮命中 → 强制 rewrite + 提示「立希不是温柔安慰式」
- **依赖**：扩展 mygo L11031 现有 guard、不另开
- **状态**：未开始

### P1 · 中期推进

#### 1.3 nickname_lock（称呼系统）
- **canon 来源**：VOICE_CONSTRAINTS §1.2 / §1.6
- **当前缺失**：LLM 偶尔把灯称作"灯灯""灯酱"——立希对灯**只**用本名零修饰、绝不加任何前缀/后缀
- **目标**：post-reply pattern match 「灯[灯酱亲ちゃん]」→ rewrite 成单字"灯"
- **状态**：未开始

#### 1.4 afterglow_disambig（蘭/巴 乐器混淆）
- **canon 来源**：VOICE_CONSTRAINTS §1.6 + character_profiles.py
- **当前缺失**：LLM 偶尔把蘭说成鼓手 / 巴说成主唱
- **目标**：post-reply 检测「蘭.*?(鼓|drum)」或「巴.*?(唱|vocal|主唱|吉他)」→ flag
- **状态**：未开始

#### 1.5 drum_dtm_workflow（鼓 / DTM 物件工作流）
- **canon 来源**：character_profiles.py 立希档案（DTM / Logic Pro / 雙踏 / Sonor Cocktail / Roland TD17）
- **当前缺失**：被问「你在做什么」「在写歌吗」时、回答太抽象、没有物件锚定
- **目标**：参考 tomori 笔记本系统、给立希做"鼓 + DAW + 谱面"物件 state
- **依赖**：tomori 笔记本系统先跑通作为模板
- **状态**：未开始

### P2 · 长期 / 视情况

#### 1.6 family_school_anchor（家庭 / 选校深层 canon）
- **canon 来源**：character_profiles.py + VOICE_CONSTRAINTS §1.6
- **触发场景**：聊到姐姐 / 真希 / 祥子 / 花咲川 / 转校
- **目标**：注入硬约束（花咲川 = 逃开姐姐学校、对真希 / 祥子的劣等感、灯是唯一安全地带）、防止 LLM 把"转校到花咲川"写成正面选择
- **状态**：未开始

#### 1.7 knowledge_qa_mode（知识问答 模式分流）
- **canon 来源**：VOICE_CONSTRAINTS §1.6
- **当前缺失**：技术问题（鼓 / 节奏 / DTM）和非技术问题 LLM 处理一致、缺立希「技术耐心 / 非技术哈？」的分流
- **目标**：本轮 user_text 触发分类、命中技术词库 → 注入「可以多说两句、但仍直接」；命中非技术 → 注入「一句话挡回去」
- **状态**：未开始

---

## 2 · 接入路径（实现时按此走）

每个子系统接入主流程的标准路径：

1. 在 `taki/turn_logic/<name>.py` 或 `taki/voice_check/<name>.py` 写实现
2. 加 env flag（如 `TAKI_VOICE_CHECK_VISUAL_CLAIM=1`）、默认开
3. 在 `taki/api.py` 的 stub 函数里 wire 实际调用
4. caller 端（mygo / chat_server）调 `taki.api.xxx`、不直接 import 子模块
5. 写 1-3 个 offline harness 到 `_test_taki_<name>.py`、能跑 deterministic 断言
6. 上线后观察 dump、确认效果

---

## 3 · 修订日志

| 日期 | 内容 |
|------|------|
| 2026-05-11 v0.0.1 | 创建 taki/ 包、VOICE_CONSTRAINTS.md 索引、`_PERSONA_FINGERPRINT["立希"]` 整合为 SSOT |
| 2026-05-12 v0.0.2 | 补全骨架：api.py（is_taki / render_supplemental_blocks / post_reply_voice_check stub）+ turn_logic/ + voice_check/ 子包 init + PROGRESS.md。所有子系统未实现、stub 永远 return ""，不影响主流程行为 |
