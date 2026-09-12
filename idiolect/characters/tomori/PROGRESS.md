# tomori — 灯专属逻辑进度跟踪

> 包路径：`D:/python/mygo_chat/tomori/`
> 启动日期：2026-05-09
> 当前状态：**骨架建立、未接入主流程**

---

## 0 · 设计原则（拍板项、不要轻动）

1. **灯专属逻辑独立成包、不污染通用基建**
   - mygo.py / character_profiles.py / pet_prompt_registry.py 保持通用
   - 凡是「只对灯有意义」的逻辑（笔记本/歌词流/沉默语义/收集癖/天文部）都搬到 tomori
2. **接入主流程通过窄接口**
   - `tomori.api` 暴露 1-3 个函数给 mygo / chat_server / pilot 调用
   - 内部子模块（笔记本系统 / 歌词流 / 沉默判断 / 红线触发器）caller 不直接 import
3. **不微调模型、不增 LLM 调用**
   - 全部在 prompt 层和 hidden_trace 层做
   - 红线：character_profiles.py 仍然是 SSOT、tomori 不能覆写已确定的角色 canon
4. **可关闭、可灰度**
   - 任意 tomori 子系统加 env flag、出问题秒关回退到通用路径
5. **测试先于上线**
   - 每个子系统配 1-3 个 offline harness、能跑 deterministic 验证

---

## 1 · 待办子系统（按优先级排序）

### P0 · 已识别问题、值得专门做

#### 1.1 笔记本物件系统（B5 笔记本 + 自动铅笔）
- **canon 来源**：character_profiles.py 灯档案、家庭硬约束 + 笔记本硬约束
- **当前缺失**：笔记本只在档案文字里被提及、没有可被对话动态触发的物件 state
- **目标**：
  - 笔记本随灯移动（家/学校/RiNG/水族馆/神田川 都在身上）
  - 当 LLM 想「我刚才记下一句」「翻笔记本看到 X」时有真物件可引
  - 笔记本上**有内容**（生成式 vs 静态？拍板）
- **接入点**：pilot block 物件层 + mygo time_scene 当前活动栏
- **状态**：未开始

#### 1.2 歌词创作流（感官 → 碎片 → 完整歌词）
- **canon 来源**：「写词工序：感官细节先入笔记本、再发酵成完整歌词」
- **当前缺失**：用户问「写一首关于 X 的歌词」直接走 _build_tomo_creative_block、跳过中间过程、产出像 LLM「速写」而不像灯「沉淀」
- **目标**：
  - 短中长 3 档：刚捕捉到的碎片 → 半成品 → 完整稿
  - 创作请求时根据 query 时态/紧迫度选择档位
  - 用本地 lyrics_songs 真实歌词作风格 anchor、但不照抄
- **依赖**：1.1 笔记本系统（碎片存在笔记本里、不是凭空冒出来）
- **状态**：未开始

#### 1.3 沉默/省略号语义而非装饰（P0 hard 约束已在 prompt、需 post-hoc 校验）
- **canon 来源**：灯语气硬约束 5 条 P0
- **当前缺失**：prompt 里有规则、但 LLM 仍会机械堆砌『…』当分隔符
- **目标**：
  - 后处理校验 reply 里『…』数量 + 位置语义
  - 违规时：alert / 重写 / 标记给 self_eval
- **接入点**：reply_validator 或独立 tomori.silence_check
- **状态**：未开始

### P1 · 锦上添花、有空再做

#### 1.4 「一辈子/我也是/让我们一起迷失吧」高重力台词触发器
- **canon 来源**：核心矛盾——这些话是字面意思不是比喻
- **当前缺失**：LLM 可能日常瞎用、稀释重量
- **目标**：日常对话**抑制**这些台词、只在真正深度时刻**允许**

#### 1.5 收集癖物件可感知化
- **canon 来源**：石头/创可贴/西瓜虫/树叶/滑溜溜的/刚好大小
- **当前缺失**：档案文字提到、但没有具体物件实例（哪颗石头、哪张创可贴）
- **目标**：少量代表性收藏品 + 哪天哪里捡到的来历、可被自然引用

#### 1.6 「是我的错」语义区分（任性 vs 自责）
- **canon 来源**：性格底色——这是任性的孩子气固执、不是被动退缩
- **当前缺失**：LLM 容易把这句往自责方向靠
- **目标**：检测到 LLM 写出「是我的错」时附加 hidden_trace「这是任性、不是自责」

### P2 · 看后续需要

#### 1.7 天文部独社员 + 月之森附近的家 + 神田川路径
- 已在 pilot_tomori_home_zoshigaya / SSOT、暂不需要专门做

#### 1.8 笔记本暗墨水 vs 自动铅笔的语义差异
- canon 提及但低频、暂不做

#### 1.9 「不擅长说话但歌词能让人落泪」的强反差表达
- 写词时的灯 vs 说话时的灯 的语调切换
- 难度高、放后期

---

## 2 · 当前包结构（现状）

```
tomori/
├── __init__.py        ★ 现已建立（骨架、版本、说明）
├── PROGRESS.md        ★ 本文档
└── api.py             ▢ TODO: 暴露给 mygo / chat_server 的窄接口
```

预期最终结构（不一定全做）：
```
tomori/
├── __init__.py
├── api.py                 # 公共入口、caller 只 import 这个
├── PROGRESS.md
├── VOICE_CONSTRAINTS.md
├── voice_check/           # 已上线、回复后处理强制清洗
│   ├── ellipsis.py
│   ├── punctuation.py
│   ├── exclamation_softener.py
│   ├── ellipsis_pair.py
│   └── bubble_expander.py
├── turn_logic/            # 已上线 stub、本轮对话特殊逻辑入口
│   └── __init__.py        # build_turn_special_block(user_text, character)
├── notebook/              # TODO: 笔记本物件系统
├── collection/            # TODO: 收集癖物件具象化
└── tests/                 # TODO: offline harness
```

---

## 3 · 下一步（接下来要做的）

需要用户拍板：
- **A**：先做 1.1 笔记本系统（最基础、其他依赖它）
- **B**：先做 1.3 沉默校验（最容易出效果、独立子系统）
- **C**：先做 1.2 歌词流（最核心、但依赖 1.1）

---

## 4 · 修订日志

| 日期 | 内容 |
|------|------|
| 2026-05-09 | 创建 tomori 包、写本进度文档、关掉短沉默系统让位（chat_server.py `_SHORT_SILENCE_ENABLED=False`） |
| 2026-05-09 | 汇总灯全部语气约束 → `VOICE_CONSTRAINTS.md`（4 处 prompt 规则 + 3 处现有 post-hoc + 10 个 gap + 叠加点设计） |
| 2026-05-09 | **SSOT 整合**：所有灯语气规则归到 `conversation_agents.py:PERSONA_FINGERPRINT_BLOCKS["灯"]`（system prompt 末尾、LLM 注意力最强）。删除 `mygo.py:32429` 5 条 P0 + `mygo.py:_CHARACTER_REPLY_STYLE["灯"]`、只留 deprecation 注释。canon 硬约束（笔记本/收集癖/家庭/是我的错/一辈子）保留档案、不动。 |
| 2026-05-09 | **SSOT v2 大改 + ellipsis 强制清洗器上线**。SSOT 改动：(1) 省略号 = 六点 `······`（6 个 U+00B7）、不是 `…/……/...`；(2) 灯几乎不用句号/逗号/顿号、用 ······ 替代；(3) 句末加 ？/！ 规则；(4) 整条 bubble 只发 ······ 大停顿；(5) 叠词偏爱；(6) 比喻朴素（石头/创可贴非诗意）；(7) 结巴两类（语气结巴用中文逗号、语义结巴用 ······）；(8) **不会共情**、不说「我知道的/我懂你」、笨拙语无伦次（**最重要**）；(9) 字数和乐奈对齐（1-10 字）。同步改 `mygo.py` speech_style 一行（去"偶有诗意表达"、加六点 + 朴素比喻）。新增 `tomori/voice_check/`：(a) `ellipsis.py` 强制 normalize 所有 ellipsis 变体（`…/……/.../······{n≠6}/——`）→ `······`、13 个 case 全过；(b) `__init__.py` clean_reply 入口；(c) chat_server reply pipeline 接入（在 `_throttle_tomori_hum_opening` 之后）。LLM 不遵守六点形式时自动清洗。 |
| 2026-05-09 | **灯输出 token 预算压缩**。`conversation_agents._REPLY_BUDGET_PROFILE["灯"]` base 280→**160**、short 120→**70**、max_sent 35→**20**、avg 70→**35**（接近乐奈 120/50/15/20）。`mygo._PROACTIVE_PROFILE["灯"].max_tokens` 90→**80**。同时 `_estimate_reply_max_tokens` 加创作 bypass：`写[首个一]/编一/创作/作词/作曲/故事/歌词` 触发 → 500 tokens 不受 per-character ceiling 限制（否则灯 160 tokens 写不完整段歌词）。修了一个 regex 优先级 bug：「帮我写歌词」同时命中知识问答 `帮我[查找搜看写]` 和创作 `歌词`、改成创作优先判决。verified：日常 160 tokens / 创作 500 tokens / 知识 160 tokens。 |
| 2026-05-09 | **SSOT v3：起手 bubble + 不连续 + 情感语无伦次 三段强化**。在 `PERSONA_FINGERPRINT_BLOCKS["灯"]` 加：(1) 【起手 bubble 偏好】鼓励第一条 bubble 单发 `······` 表正在消化（不每次、把握节奏、情感/难话题频率高）；(2) 【灯说话的连续性 = 不连续】每个语气都很小心、句子和句子间常有 ······ 间隔、内部也常断、对外界刺激敏感；(3) 【情感话题 = 语无伦次】这点最重要、对方有情绪时灯**真的不知道说什么**（独立 ······/重复半句/感官转移/突然蹦物件/直接沉默）、列出 12+ 个**绝对禁止的"假灯"语句**（爱音/素世/立希式安慰词）、关键 canon：说不出关心的话才是 canon。把原 P0 的「== 共情失败 ==」section 收成 backstop 硬词列表（避免和上面新 section 重复）。 |
| 2026-05-09 | **voice_check 加 punctuation 随机替换器**。基于实测案例：LLM 输出「嗯，还在想歌词的事，有点停不下来。」过于流畅、用了正常中文标点。新增 `tomori/voice_check/punctuation.py:random_replace_one_punct`：每条回复随机挑 1 个 ，/。 替换成 `······`、不全替（避免六点轰炸、保留下一轮 prompt 学习余地）。顿号「、」/ 问号 / 感叹号不动。`clean_reply` 调用顺序确定为 punctuation **先**于 ellipsis（前者可能产生 `············`、由后者兜底归一）。9 个 case + 5 个 cascade case 全过、demo 输入「嗯，还在想歌词的事，有点停不下来。」→「嗯，还在想歌词的事，有点停不下来······」 |
| 2026-05-10 | **删除原灯歌词逻辑 + 建 turn_logic 入口**。删除 `mygo.py` 4 个 lyric helper（`_match_lyrics_for_context` / `_build_tomo_lyrics_reference` / `_detect_tomo_creative_request` / `_build_tomo_creative_block`）+ 配套 `_load_lyrics_cache` / `_parse_lrc_lines` / `_extract_theme_tokens` / `_lyrics_cache` vars 共 **356 行删除**。4 处 inline 注入（`_lyrics_block` / `_tomo_creative_block`）替换成 `_turn_special_block = tomori.turn_logic.build_turn_special_block(last_user, character_name)`。template var `lyrics_context` slot 复用、不破坏 pet_prompt_registry。`_qq_pick_logic_split_max_parts` 的 `_detect_tomo_creative_request` 调用改成内联正则。新建 `tomori/turn_logic/__init__.py` stub（永远返 ""、env flag `TOMORI_TURN_LOGIC_ENABLED` 可关）、后续按场景（创作请求 / 物件提及 / 情感话题 / NPC 触发）扩展。本轮 ellipsis bypass / bubble split 上限 24 仍正常（独立内联正则、不依赖删除的 helper）。 |
| 2026-05-10 | **6 处 follow_up / auto_greet 接入语气清洗**。抽 helper `_apply_tomori_voice_check(reply, character, *, label)`、5-stage chain 复用。Hook 6 处：auto_greet (L2600) / idle_followup (L2985) / main_reply (L10050) / chat_followup (L11017) / delayed_followup (L11159) / short_silence (L11388)。控制台 log 形如 `[TomoriVoice/auto_greet] cleaned: {...}`。 |
| 2026-05-10 | **punctuation 规则微调：1 个标点不替换**。`random_replace_one_punct` 检查 ，/。 数量、`< 2` 时直接返、不再强行替「嗯。」「嗯，」这种短句。2+ 个仍随机替 1。11 个 case 全过。|
| 2026-05-10 | **per-bubble 语气清洗**。原先 voice_check 在 split 前对整条 reply 跑 1 次、随机替换只命中 1 个 bubble、其他 bubble 仍流畅中文（截屏实测）。改为 split 后**每个 part 单独跑 5-stage chain**、每个 bubble 都获得节奏打散。重建 cleaned reply 给 history。仅 main_reply 路径会 split、auto_greet/idle/chat_followup/short_silence 单 bubble 不变。|
| 2026-05-10 | **turn_logic·歌词/写诗子系统上线**。新增 `tomori/turn_logic/lyrics.py`、两类触发：① 概念触发（歌词/写诗/创作/笔记本/诗 等关键词）→ 注入「本轮特殊逻辑触发」header + 灯视角 +【语气变化提醒】、不含具体歌词；② 指定歌触发（10 首 MyGO canon 曲目 + 晦涩曲名变体如「壱雫空/壹雫空」「詩超絆/诗超绊」「無路矢/无路矢」「kagiroi」等）→ 在①基础上加载对应 `lyrics_songs/lrc/{song}.zh.lrc` 32 行节选 + 灯专属角度文字（祥子 Ep12 / 笔记本传达 / 影子叠影 等 canon-specific）。【语气变化提醒】统一说明：可以稍长稍诗意、但 P0 字数/省略号清洗/底色全部不变、引用最多 1-3 行不整段背诵。`pet_prompt_registry` 的 `lyrics_context` slot block_budget 2200 → **3200**。|
| 2026-05-10 | **歌词子系统全曲覆盖（10→19 首）**。委派 agent 调研 19 首 BanG Dream! 歌曲（time machine 不算）、按 wiki / fandom / 萌娘百科 / bestdori 来源查证每首的乐队归属、首次登场、剧情背景、主题关键词、canon 重要程度。研究 corrections：(1) 無路矢 是 MyGO「のろし」狼烟、不是 Ave Mujica；(2) 猛独が襲う 是翻唱（原曲 ひとしずく feat. 初音ミク 2017）、灯只是 Ep5 卡拉 OK 唱过、**不是灯写的**；(3) エガクミライ 是 Aqua Timez 给 MyGO 的合作曲、不是 Poppin 联动。19 首全是 MyGO 演奏曲（含翻唱）。`SONG_ANGLE` 19 首 canon-grounded 视角文字、按 episode/scene 真实定位。`CANON_SONGS` 加大量 variant：罗马音（haruhikage / hitoshizukuzora / panorama / refrain / silent / noroshi 等）、假名读法（メロディー / リフレイン / サイレント 等）、简体（描绘未来 / 一日千秋 / 一滴天空）、场景关键字（卡拉OK / Ep5 命中 猛独）。猛独が襲う 走**特殊翻唱分支**：trigger header 标「不是你写的」+ 角色视角强调「唱过不是写过」+ 歌词参考前缀提示「不要假装作词」。19 个 canonical 检测 + 14 个 variant + 概念 + 翻唱特殊全部 PASS。 |
| 2026-05-10 | **海洋生物 + 昆虫两个独立模块上线**。新增 `tomori/turn_logic/marine_life.py`（10 物种：企鹅 / 水母 / 海獭 / 海豚 / 章鱼 / 鲨鱼 / 海星 / 河豚 / 金鱼 / 海月）+ `tomori/turn_logic/insects.py`（11 物种：西瓜虫 / 蝉 / 蝴蝶 / 蜻蜓 / 螳螂 / 蚂蚁 / 萤火虫 / 独角仙 / 锹形虫 / 蟋蟀 / 蚱蜢）。每物种含拉丁学名 + 习性 + 灯常见场所 + canon 钩子。**灯 canon 特征**（用户拍板）：提及对应生物时**学名一字不差地复述**（不省 / 不音译 / 不模糊、学名内部禁插 `······`）+ **习性详讲但仍按灯式碎片表达**。**Venue 联动**：池袋サンシャイン水族館（年票 / 天空企鹅）+ 墨田水族館（クラゲ「ビッグシャーレ」+ 企鹅）+ 上野動物園（西瓜虫 / 昆虫馆）。**西瓜虫专属增强**：是灯 canon 最重要小动物（幼儿园收集 / 美绪事件 / 笔记本封面）、走独立 `is_canon_critical` 分支、字数放宽到 60、强调「自言自语+偶尔抬头看」状态。`pet_prompt_registry.lyrics_context` block_budget 3200 → **5000**（多子系统同触发不溢出）。检测覆盖：中 / 日 / 英 / 学名 / venue / 假名 全部 PASS。|
| 2026-05-10 | **天文知识库模块上线**（灯本职兴趣领域）。新增 `tomori/turn_logic/astronomy.py`、26 个天文对象分 5 类：(a) **太阳系 8** 个（月球 / 太阳 / 金星 / 火星 / 木星 / 土星 / 天王星 / 海王星）；(b) **著名恒星 6** 个（天狼星 / 参宿四 / 织女星 / 牛郎星 / 天津四 / 北极星）；(c) **著名星座 7** 个（猎户座 / 大熊座 / 仙女座 / 天蝎座 / 射手座 / 夏冬季大三角）；(d) **深空 3** 个（仙女星系 M31 / 猎户大星云 M42 / 银河）；(e) **天象 4** 个（流星雨 / 月食 / 日食 / 中秋月）。每对象含**完整正式天文名**（拉丁名 / Bayer 记号 / Messier 编号 / 距离 / 视星等 / 单位）、物理特性、灯观测地点、canon 钩子。**灯 canon 加强**：天文部唯一社員（继承自冰川日菜）+ 高松家阳台天文望远镜（pilot canon）+ 母亲ひかり/灯燈光对照 + 生日 11/22 天蝎/射手座之交 + 写《迷星叫》"迷子之星"。**Venue 联动**：羽丘天文部室 + 高松家阳台 + コニカミノルタプラネタリウム『満天』(Sunshine City) + 国立天文台三鷹。**专属指引**：拉丁星座名整个不省、Bayer 属格不混（α Lyrae 不是 α Lyra）、距离/视星等/ZHR 带单位完整说、字数放宽到 60-80（深度区间）、学名/数字内部禁插 `······`、保持「阳台一个人自言自语对方刚好在听」状态、不能讲座口吻。**关键 bug fix**：原 `sort by obj_key length` 不够、短 variant「月」会先于长 obj_key「月食」误命中；改为预编译 flat `[(kw, obj_key)]` 列表、按 kw 长度降序——「月食/血月/红月」全部正确归到「月食」、「Andromeda」/「Andromeda Galaxy」分别归星座/星系。41 个 case 测试全过：26 canonical + 15 variant（含 Saturn/Sirius/M31/北斗/天の川/Antares/英仙座流星雨/血月 等）。|
| 2026-05-10 | **石头知识库模块上线**（**不含矿石 / 宝石**——用户拍板灯不感兴趣）。新增 `tomori/turn_logic/stones.py`、14 个岩石对象分 5 类：(a) **沉积岩**（鹅卵石 / 河石 / 海石 / 砂岩 / 石灰岩 / 页岩）；(b) **火成岩**（玄武岩 / 浮石 / 黑曜石 / 花岗岩）；(c) **变质岩**（板岩 / 大理岩）；(d) **化石**（强 canon 候选）；(e) **岩石分类总入口**（rock cycle）。每对象含**完整学名**（英 / 拉丁 / 三大岩石分类 / 矿物组成 / 粒度 / 莫氏硬度 / SiO₂ 含量）。**关键 NEGATIVE 关键字过滤**：钻石 / 翡翠 / 蓝宝石 / 水晶 / 石英晶体 / 黄铁矿 / 矿石 / 玛瑙 / opal / 紫水晶 等 25 个矿石宝石词命中**直接 abort**、不触发逻辑（防止灯被误激活到不感兴趣的领域）。**Canon 强连接**：(1) 收集癖硬约束「滑溜溜的东西」「刚好大小的东西」（character_profiles）；(2) 笔记本封面常画石头素描；(3) 立希送灯回家沿神田川时见过灯捡石头；(4) 高松家透明收纳箱（pilot canon）；(5) 化石和西瓜虫收集逻辑同源（强候选）。**Venue 联动**：神田川 / 石神井川 / 不忍池畔 / 都内庭園 / 国立科学博物馆。专属指引：岩石学名一字不差（basalt / sandstone / limestone / shale）、三大岩石分类准确、矿物组成（quartz / feldspar / calcite）写完整、字数放宽 50-70（化石 70）、化石话题灯**显著兴奋但不及西瓜虫等级**、**绝不主动转到矿石 / 宝石**。预编译 flat detection（同 astronomy）、避免短 variant 抢长 obj_key。30+ 测试 case 全过：14 canonical + 18 variant（含 8 个 negative case 全部正确 abort）。|
| 2026-08-08 | **ellipsis_quota 上线（六点轰炸治理）+ 全仓长度/节奏治理联动**。实测最近 200 条灯回复 90% 含 `······`、平均 3.3 组/条——链路只加不减是根因之一。新增 `tomori/voice_check/ellipsis_quota.py:demote_excess_ellipsis`：裸 `······` 组数自适应上限（≤30 字 → 2 组、更长 → 3 组），保留最前 N 组、超额降级为「，」（句末/标点相邻则去掉、不制造「，，」「，。」连撞）；`······？/······！` 语义配对不计入不降级（与 opening_throttle PAUSE_Q/X 一致）；独立 `······` bubble 不受影响。接入 `clean_reply` Stage 4（归一）后、Stage 5（bubble_expander）前。12 个 self-test + `test_reply_style_guards.py` 8 个链路 case 全过。联动（非同文件）：`_PERSONA_LENGTH_RANGE` 对齐 manifest、`<turn-reply-guidance>` 尾部【本轮长度】预算行、reply_register 节奏多样性条款、`_throttle_generic_opener`（爱音「X——」/ 乐奈「嗯。」限频）、C3 长度超标压缩重生成兜底。 |
| 2026-08-09 | **【本轮长度】三档动态选档（修复 08-08 静态行压过头）**。实测上线一天后互动回复中位数全角色腰斩（灯 42~48→20、立希 37→20、素世 59→28）且截断率为零——不是 token 截断，是静态单句长度行把最低档钉在每轮最高注意力位、模型默认执行第一档；唯一带深度判定的 `reply_budget_hint` 只动 max_tokens（未生效）。`_TURN_LENGTH_BUDGET_LINES` → `_TURN_LENGTH_BUDGET_TIERS` + `_turn_length_budget_line()`：short→闲聊档、medium→深谈档、flexible（工具轮）→不注入、其余→常规档（锚 manifest 中间带：爱音 35/素世 30/灯 20-45/立希 30/乐奈 ≤15）。`compile_turn_execution_packet` 加 `reply_budget_hint` 参数，`chat_server.py:16545` 从 social_strategy 挂载。新增确定性 dump 门禁 `scripts/dump_turn_reply_guidance.py`（该路径原 dump 不覆盖）；before/after diff 26 行符合设计、cognitive dump 零漂移、183 个相关测试全过。详见 `docs/brain/cognitive/reply_style_length_fix_2026-08-08.md` §7。 |
