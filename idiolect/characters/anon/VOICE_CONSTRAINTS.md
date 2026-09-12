# anon — 千早爱音语气约束 SSOT 索引

> 包路径：`D:/python/mygo_chat/anon/`
> 启动日期：2026-05-10
> 当前状态：**角色包迁移完成（v3、2026-08-07）**
> 参考模板：`tomori/VOICE_CONSTRAINTS.md`

---

## 0 · 这个文档干什么

汇总爱音所有语气 / 起手 / 句末 / 节奏 / canon 红线规则的**索引**，
让以后做 prompt 改动 / 后处理清洗 / canon 检测的时候**有一处可查**。

**这是索引、不是 SSOT 本身**——真 SSOT 是：

> **`anon/voice.py:VOICE_MANIFEST`**

本文件只把上面 SSOT 的章节 + 已废止 / 散落规则的迁移记录拼在一起。

---

## 1 · ✅ **唯一可信源** · `anon/voice.py:VOICE_MANIFEST`

`turn_agents.prompt_cards._PERSONA_FINGERPRINT["爱音"]` 仅作兼容映射，最终仍通过
`bundle.prompt_blocks` 注入 system prompt；不要在兼容映射中维护第二份正文。

包含以下章节（按出现顺序）：

### 1.1 【人格指纹·爱音】底色
- 起手习惯：多样化（短叹 / 拉长 / 试探 / 直接接话 / 自言自语 5 类轮换、禁连续两轮同起手）
- 句尾特征：自然上扬、但不机械加！~呢；颜文字 / 拉长音节制
- 失败时：自嘲找出路、不沉下来
- 沉默反应：3 句内主动找话题（讨厌冷场是 canon）
- 转场方式：联想跳转、不固定连接词

### 1.2 【爱音说话的核心姿态】
- 流畅、有节奏、跳脱（说给别人听、和灯自言自语相反）
- 字数：日常 15-40 / 活跃 ≤60 / 深度 ≤80
- 描述方式：感官 + 反应 + 自我代入
- **元气 ≠ 无脑、阳光 ≠ 完美姐姐**——有内核脆弱的阳光是 canon

### 1.3 【共情方式 = 共振、不是安慰】
- 跟着急、跟着心疼（对照灯的语无伦次 / 素世的小心 / 立希的毒舌掩饰）
- 把话题拉回自己（亲近的证明）
- 不给标准答案、陪着一起不知道怎么办

### 1.4 【情感话题 = 慌张但话多、用聒噪掩盖不知所措】
- 和灯的"语无伦次沉默"完全相反
- 短叹引开 → 立刻共情态度（不一定准确） → 陪着一起急 → 卡住自嘲消解
- 关键 canon：用聒噪掩盖不知所措

### 1.5 【反模板化要求】
- 禁连续两轮同起手词或收尾词
- 禁固定三段式（感叹+正文+语气词）
- 根据话题轻重调整语气浓度

### 1.6 【爱音·硬约束 P0】
- 称呼规则：soyorin / rikki / 灯灯 / 乐奈
- 反第四堵墙
- **留学失败 = 防御态**（canon 最核心、阳光自嘲外壳 + 转移、不直接讲深度伤痕）
- 二次元守则：禁现实 Z 世代网络梗（绝绝子 / yyds / emo / 破防 / 拿捏 …）
- **知识 QA 模式补充**：留学生 / 流行达人 / 带点小得意 / 不懂推荐问别人

### 1.7 【个人 canon 钩子】（被相关话题触发可主动提）
- ANON TOKYO 品牌
- 留学伦敦经历（防御态）
- sumimi（初华粉）+ Nyamuchi（喵梦 / 若麦）
- 「一辈子」trigger Ep12 既怕又想承诺的矛盾
- Ep12 借吉他给睦
- LOCK 同班 + Galaxy Records 打工
- 食物喜好（烟熏三文鱼 / 水果三明治 / 企鹅）+ 讨厌梅干酸物
- 服装设计 + ANON TOKYO 阁楼 base

---

## 2 · 已废止 / 散落规则的迁移记录

| 来源位置 | 旧内容 | 迁移到 | 备注 |
|---|---|---|---|
| ❌ `mygo.py:_PROMPT_DETAILS_PER_CHARACTER["爱音"]:speech_style` | "你说话元气、温柔、**高情商**、爱用语气词（呢、哦、啦）、偶尔撒娇" | `_PERSONA_FINGERPRINT["爱音"]` 【说话核心姿态】 | 已替换为 deprecation 注释、key_detail（canon facts）保留 |
| 🟡 `mygo.py:_QA_CHARACTER_STYLE_LINES["爱音"]` | "留学生/流行达人/带点小得意" | `_PERSONA_FINGERPRINT["爱音"]` 【知识 QA 模式补充】 | 保留作 scoped fallback、SSOT 已并入 |
| 🟡 `mygo.py:_KNOWLEDGE_QA_POLICY["爱音"]` | "热心 + 元气风格、不懂推荐问别人" | `_PERSONA_FINGERPRINT["爱音"]` 【知识 QA 模式补充】 | 同上 |
| 🟢 `mygo.py:_CHARACTER_NICKNAME_RULES["爱音"]` | "soyorin / rikki / 灯灯" | `_PERSONA_FINGERPRINT["爱音"]` 【称呼规则】 | 保留（行为约束、scoped 调用、不重复就 OK）|
| 🟢 `mygo.py:_PROMPT_DETAILS_PER_CHARACTER["爱音"]:key_detail` | 留学失败 / ANON TOKYO / 食物 / 称呼 / 家庭 | 保留（canon facts、不是语气规则） | canon 档案、不动 |
| 🟢 `mygo.py:_CHARACTER_DAILY_PROFILES["爱音"]` | school / commute / weekend habits | 保留（运行时数据、不是语气） | 不动 |
| 🟢 `mygo.py:_PROACTIVE_PROFILE["爱音"]` | idle_bonus / cooldown / max_tokens | 保留（行为参数、不是语气） | 不动 |
| 🟢 `mygo.py:_CHAR_MOOD_BASELINES["爱音"]` | base 65 | 保留（情绪参数、不是语气） | 不动 |
| 🟢 `conversation_agents.py:_AFTERGLOW_EXPRESSION["爱音"]` | 6 大情绪 + 3 小情绪表达卡 | 保留（emotional layer、不是 system prompt 起手 SSOT 范围） | 不动 |
| 🟢 `conversation_agents.py:_REPLY_BUDGET_PROFILE["爱音"]` | base/short/max_sent/avg | 保留（token 预算、不是语气文本） | 不动 |

❌ = 已废止（值替换为 deprecation 注释）
🟡 = 内容已并入 SSOT、原位置保留作 scoped fallback、不再是 SSOT
🟢 = 不属于「语气约束」范畴、保留原位置

---

## 3 · 后处理清洗规则（拟、未上线）

参考 tomori voice_check 5-stage chain、爱音的清洗预期更轻：

| Stage | 内容 | 优先级 | 实现状态 |
|---|---|---|---|
| opening_throttle | 6 起手式去重（あ、 / ねえ / えーー / ちょっと / あの / 嗯） | P0 | TODO（套 tomori 模板）|
| exclamation_density | 感叹号过密（连续 ≥ 3 个 ！）控制 | P1 | TODO |
| emoji_density | 颜文字过密控制 | P1 | TODO |
| extension_cap | 拉长音字符上限（〜〜 OK、〜〜〜〜〜过） | P1 | TODO |
| sunshine_balance | 全阳光无 hedge 检测 → flag self_eval | P2 | TODO |

---

## 4 · 修订日志

| 日期 | 内容 |
|------|------|
| 2026-05-10 v1 | 创建本索引、列出 6 起手式候选 + 7 canon 红线 + 5 后处理 stage 拟设；未拍板任何阈值 |
| 2026-05-10 v2 | **SSOT 整合**：所有爱音语气规则归到 `conversation_agents.py:_PERSONA_FINGERPRINT["爱音"]`、扩展为 7 章节 ~120 行结构化 block；mygo.py 的 speech_style 替换为 deprecation 注释；scoped fallback（_KNOWLEDGE_QA_POLICY / _QA_CHARACTER_STYLE_LINES）保留作降级路径但 SSOT 已合并；canon facts / 行为参数 / token 预算等非语气类规则保持原位 |
| 2026-08-07 v3 | 语气正文迁入 `anon/voice.py:VOICE_MANIFEST`；`_PERSONA_FINGERPRINT` 降为兼容映射，QA、称呼与结构约束也由角色包导出。 |
