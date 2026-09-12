# anon — 千早爱音专属逻辑进度跟踪

> 包路径：`D:/python/mygo_chat/anon/`
> 启动日期：2026-05-10
> 当前状态：**骨架建立、未接入主流程**
> 参考模板：`tomori/PROGRESS.md`（结构和原则照搬）

---

## 0 · 设计原则（拍板项、不要轻动）

1. **爱音专属逻辑独立成包、不污染通用基建**
   - mygo.py / character_profiles.py / pet_prompt_registry.py 保持通用
   - 凡是「只对爱音有意义」的逻辑（留学防御 / 灯灯粘着 / sumimi / Ave Mujica 复合）都搬到 anon
2. **接入主流程通过窄接口**
   - `anon.api` 暴露 1-3 个函数给 mygo / chat_server / pilot 调用
   - 内部子模块（turn_logic / voice_check / 起手式追踪）caller 不直接 import
3. **不微调模型、不增 LLM 调用**
   - 全部在 prompt 层和 hidden_trace 层做
   - 红线：character_profiles.py 仍然是 SSOT、anon 不能覆写已确定的角色 canon
4. **可关闭、可灰度**
   - 任意 anon 子系统加 env flag、出问题秒关回退到通用路径
5. **测试先于上线**
   - 每个子系统配 1-3 个 offline harness、能跑 deterministic 验证
6. **复用 tomori 已验证的模式**
   - 3 层渐进激活（Tier 0/1/2）+ per-session dedup + canon override 已经在 tomori 跑通、
     scope-相似的爱音子系统直接套这个模式

---

## 1 · 待办子系统（按 canon 重要度初排、未拍板）

### P0 · 强 canon、值得专门做

#### 1.1 留学失败防御层（canon 最核心)
- **canon 来源**：character_profiles 爱音档案——伦敦留学失败、回国之后的伤痕、对外是阳光自嘲、对深问会防御
- **当前缺失**：LLM 处理「留学」/「伦敦」/「英语」/「国外」相关话题时容易直接讲深度伤痕（破 canon）
  或者过度阳光化（稀释 canon）
- **目标**：
  - 检测留学相关 keywords → 注入「**防御态**」prompt
  - 防御 ≠ 不说、是**用阳光自嘲外壳**转移（「啊那段啊~已经过去啦~」+ 立刻换话题）
  - 真深度 only 在 trust-high + 明确深问 + 适当 mood 时才允许
- **接入点**：anon.turn_logic.london_defense
- **状态**：未开始

#### 1.2 灯灯（粘着 canon）特殊柔软切换
- **canon 来源**：character_profiles 关系矩阵——爱音对灯有特殊温度、call sign「灯灯」
- **当前缺失**：LLM 容易把这变成普通"喜欢同伴"、稀释 canon 的接触欲 / 黏度
- **目标**：
  - 提到灯 / 高松灯 / 灯灯 → 注入「特殊柔软」prompt（不是恋爱、是想接近 / 担心 / 想被看见）
  - call sign 频率控制：canon 但不能每条都喊
  - 和 marine_life canon override（爱音+水族馆）联动：那是从灯方向看、这是从爱音方向看
- **接入点**：anon.turn_logic.tomori_special
- **状态**：未开始

#### 1.3 起手式去重（参考 tomori opening_throttle）
- **canon 来源**：爱音口癖——「ねぇ」/「えーー」/「あ、」/「ちょっと」/「あの」高频、但 LLM 一旦学会就过载
- **当前缺失**：没有起手式追踪、爱音很容易「连 5 条都用 ねぇ 起手」
- **目标**：
  - 6 类起手式（仿 tomori 6 起手式架构）独立 kind 计数
  - 同 kind 前 3 条里 ≥ 2 条 → 压制本条（剥头、不替换、保留无起手也是好的）
  - 拉长音处理：「ねぇーー」「えええ」字面长度控制
- **依赖**：tomori/voice_check/opening_throttle.py 模式可直接套
- **状态**：未开始

#### 1.4 阳光外壳 / 内核脆弱二分检测
- **canon 来源**：「都市丽人完美姐姐」假设阳光是 canon 误读
  爱音 canon 是**有内核脆弱的阳光**、不是无忧无虑
- **当前缺失**：LLM 容易写成纯阳光、丢失反差
- **目标**：
  - 检测过度阳光化输出（连续 3 个感叹号 / 颜文字过密 / 没有任何 hedge / 全长方面带哭腔的同时也快乐）
  - flag 给 self_eval / 警告 prompt 加内核脆弱锚

### P1 · 锦上添花、有空再做

#### 1.6 sumimi 真奈粉丝兴奋
- **canon 来源**：character_profiles SSOT line 3892——爱音 sumimi 粉丝、MyGO アカ followed 真奈
- **当前缺失**：触发时无 canon 加权
- **目标**：sumimi / 真奈 命中 → 注入「粉丝兴奋」prompt（和普通 NPC 不一样）

#### 1.7 Ave Mujica（祥子 / 睦）复合情绪
- **canon 来源**：Ep12 爱音借吉他给睦演奏《春日影》→ 短期深共鸣
- **当前缺失**：祥子 / 睦相关话题没特殊处理
- **目标**：祥子 / 睦 / Ave Mujica → 注入「Ep12 借吉他记忆」prompt（罕见、强情感）

#### 1.8 LOCK（朝日六花）同班 + Galaxy Records 打工
- **canon 来源**：character_profiles SSOT——LOCK 是 RAS 成员、爱音同班
- **当前缺失**：触发率低、但 LOCK 提及时无 canon 加权
- **目标**：LOCK / 朝日六花 / Galaxy Records → 注入「同班 + 朋克 vs 流行口味碰撞」prompt

### P2 · 看后续需要

#### 1.9 SNS / 自拍 / 颜文字 风格 surface（pilot 物件层）
- canon 提及 SNS 但低频、暂不做

#### 1.10 英语流畅 / 留学失败的反差自嘲
- 子集于 1.1 留学防御层、不单独建

---

## 2 · 当前包结构（现状）

```
anon/
├── __init__.py            ★ 现已建立（骨架、版本、说明）
├── PROGRESS.md            ★ 本文档
├── VOICE_CONSTRAINTS.md   ★ 语气约束 SSOT 索引（待补充）
├── api.py                 ★ 公共入口 stub（is_anon / render_supplemental_blocks / post_reply_voice_check）
├── voice_check/           ★ Stage 1 ellipsis 已上线、Stage 2-4 已 mood-gate
│   ├── __init__.py        #     clean_reply (4 stages with mood gate)
│   └── ellipsis.py        #     爱音 ······ canonical normalize
├── voice_mood.py          ★ voice_mood + empathy_value + 8 mood prompts (上线)
└── turn_logic/            ★ 本轮特殊逻辑入口（2026-05-10 启动）
    ├── __init__.py        #     build_anon_special_block(user_text, character, *, session_id)
    ├── cosmetics.py       #     ✦ 美妆 / 化妆品（3 层渐进激活 + 喵梦 canon override）
    ├── fashion.py         #     ✦ 穿搭 / 服装设计（3 层 + ANON TOKYO + 素世「时尚霸凌」双 canon override）
    ├── social_media.py    #     ✦ 社交平台 / 网络媒体（3 层 + MyGO SNS 担当 canon override）
    └── london_defense.py  #     ✦ 留学失败防御态（**心理 canon、不是知识库**、5 motive posture + 1 轮余波）
```

预期最终结构（参考 tomori、不一定全做）：
```
anon/
├── __init__.py
├── api.py
├── PROGRESS.md
├── VOICE_CONSTRAINTS.md
├── voice_check/             # ✓ Stage 1 ellipsis、Stage 2-4 mood-gated
│   ├── __init__.py
│   ├── ellipsis.py
│   └── (TODO opening_throttle.py / exclamation_density.py)
├── voice_mood.py            # ✓ voice_mood + empathy_value (上线)
├── turn_logic/              # 本轮特殊逻辑入口
│   ├── __init__.py          # ✓ build_anon_special_block 已建
│   ├── cosmetics.py         # ✓ 美妆 / 化妆品（已上线、未接主流程）
│   ├── fashion.py           # ✓ 穿搭 / 服装设计（已上线、未接主流程）
│   ├── social_media.py      # ✓ 社交平台 / 网络媒体（已上线、未接主流程）
│   ├── london_defense.py    # ✓ 留学失败防御态（已上线、心理 canon 不是知识库、未接主流程）
│   ├── tomori_special.py    # TODO P0 灯灯粘着特殊柔软
│   ├── sumimi_fan.py        # TODO P1 真奈粉丝兴奋
│   └── ave_mujica_canon.py  # TODO P1 Ep12 借吉他复合情绪
└── tests/                   # TODO: offline harness（cosmetics 自带 self-test）
```

---

## 2.5 · 已建子系统详情

### 2.5.1 · turn_logic/cosmetics.py（美妆 / 化妆品）— 2026-05-10

**架构**：仿 `tomori/turn_logic/marine_life.py`、3 层渐进激活 + canon override + per-session dedup。

**12 个类别 × ~50 个具体单品**：
- 口红 / 唇釉（YSL 421 / Dior 999 / Chanel Coco / ROMAND / CANMAKE / OPERA）
- 眼影盘（Pillow Talk / NARS Climax / Maquillage / ETUDE / CANMAKE）
- 腮红（NARS Orgasm / CANMAKE 棉花糖 / 3CE / Cezanne）
- 底妆（Armani 大师 / CPB / YSL 黑管 / Maquillage / Suqqu）
- 睫毛膏 + 眼线（HEROINE MAKE / OPERA / K-Palette / DEJAVU / CANMAKE）
- 眉妆（Cezanne 双头 / KATE 三色 / Excel 染眉 / INTEGRATE）
- 防晒（Anessa 金瓶 / Bioré 蓝管 / La Roche-Posay / 樱花瓶）
- 香水（Jo Malone / Diptyque / Chanel Chance / Maison Margiela）
- 美甲（OPI / uka 护甲油 / CANMAKE Colorful / 美甲沙龙）
- 美瞳 / 假睫（Decorative Eyes / FAIRY / EYELASH SALON）
- 护肤（SK-II / 兰蔻小黑瓶 / 黛珂紫苏水 / Hatomugi / FANCL 卸妆油）
- 美容工具（ReFa / Panasonic / Salonia / Refa Beautech）

**爱音 vs 灯口吻关键差异**：
- 灯报学名 / 拉丁文一字不差 → 爱音报色号 / 型号一字不差（不音译、不简写）
- 灯讲座 ✗ → 爱音「博主 / 朋友安利」语气、不用百分比 / 化学式
- 灯 ······ 主导 → 爱音 ♪ ~ —— 主导、······ 偶用
- 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50
- 反问癖：「诶？」/「你也用过吗~」/「果然还是 X 吧？」

**喵梦 / 若麦 canon override**（最高优先级、override Tier 0-2）：
- canon 来源：character_profiles.py L4819-4821（爱音粉 Nyamuchi Channel）+ L80-81（偶像 sumimi 真奈 + 喵梦后来都成了 Ave Mujica 成员、爱音的「对家成员」复合感）
- 触发：用户提 喵梦 / 喵姆亲 / 若麦 / Nyamuchi / Amoris 任一关键字
- 注入：粉丝兴奋 + 微妙复合（「诶······Ave Mujica 那个鼓手······」式认知差）
- 防误命中：「若叶」单字易撞地名 / 树叶、需上下文 ±15 字含「喵 / Mujica / 鼓手 / 频道 / 推荐」等才触发

**接入状态**：未接主流程。函数已 export、`anon.api.render_supplemental_blocks` 还是 stub。
下一步：把 `build_anon_special_block` 接到 `chat_server` 的 anon 系统 prompt 注入点（参考 tomori 的 `lyrics_context` slot 接法）。

**测试**：`py anon/turn_logic/cosmetics.py` 内含 detect / build / dedup 三组 self-test、全部 PASS（25 detect cases + 5 build cases + 3 dedup cases）。

**Flag**：`ANON_TURN_LOGIC_ENABLED=0` 关 turn_logic 整体；`ANON_COSMETICS_LOGIC_ENABLED=0` 单独关 cosmetics。

### 2.5.2 · turn_logic/fashion.py（穿搭 / 服装设计）— 2026-05-10

**架构**：仿 cosmetics、3 层渐进激活 + per-session dedup + **2 个 canon override**。

**10 个类别 × ~50 个具体单品 / 品牌**：
- 连衣裙（SLY / LOWRYS FARM / chuu / WEGO / 灰格纹 canon）
- 上衣（UNIQLO U 白衬衫 canon / BEAMS BOY / X-girl / Champion / John Smedley）
- 外套（BEAMS / Lululemon Scuba / Dickies-Carhartt / Mackintosh / TNF Purple Label）
- 裤装（Levi's 501 / A.P.C. petit standard / GU / Acne Studios / WC Cargo）
- 裙装（Levi's mini / SLY 百褶 / Stussy x SLY / WC 伞裙 / 原宿古着）
- 鞋（NB 9060 / Nike Dunk Low / Adidas Samba / Dr. Martens / 棕色乐福鞋 canon）
- 包（COACH Tabby / BAOBAO ISSEY MIYAKE / L.L.Bean Tote / Marc Jacobs / GUCCI Y2K）
- 配饰（心形项链 canon / Vivienne Westwood 土星 / Tiffany T / Chrome Hearts / ISSEY MIYAKE Pleats）
- 帽子（New Era / Champion bucket / BEAMS beret / KAVU outdoor）
- 袜（TABIO / Tutuanna / ATSUGI ASTIGU / 渔网长袜）

**3 个 canon 实体（不指定品牌、character_profiles 直接锚的）**：
- **灰格纹连衣裙**（连衣裙类）— L97 常服 SSOT
- **棕色乐福鞋**（鞋类）— L98 羽丘制服 SSOT
- **心形项链**（配饰类）— L97 常服 SSOT

**Canon override 1：ANON TOKYO / 服装设计 / 队名提案**（最高优先）
- canon 来源：character_profiles.py L60（自创品牌）+ L61-69（曾被提议作队名 / 4 候补全包含自己名字 / 全员否决 / 最终用了灯的 MyGO + 5!）+ L57（演出服设计担当）+ L154 / L320-322（曾用设计逃避练琴、后来打破）+ L778（多才多艺浅尝辄止）
- 触发：用户提 `ANON TOKYO` / `服装设计` / `自创品牌` / `你设计` / `队名提案` / `演出服设计` / `UnKnown` / `あのね` / `Annouimo`
- 注入复合心情：**自豪有自己品牌 + 队名被否决的小遗憾 + 曾用作逃避练琴的自觉 + 多才多艺浅尝辄止**
- 防误命中：`UnKnown` / `あのね` / `Annouimo` 单字易撞英文 unknown / 日常虚词、需上下文 ±20 字含「队名 / バンド名 / 名字 / 提案 / 候选 / MyGO」等

**Canon override 2：素世「时尚霸凌」**（最高优先）
- canon 来源：character_profiles.py L4083（素世经常吐槽爱音的品味"这件衣服颜色太俗气了"，但逛街时最终总是素世在帮爱音挑衣服、整理领口）
- 触发：素世 + 衣服/品味 词汇**双 trigger 必须同时命中**
  - name 列表：素世 / soyorin / Soyorin / ソヨリン / そよりん / 长崎素世 / そよ
  - vocab 列表：挑衣服 / 选衣服 / 整理领口 / 帮我挑 / 品味 / 俗气 / 好俗 / 好土 / ダサい / 吐槽 / 嫌弃
- 注入复合心情：**表面被吐槽假装受伤 + 心里依赖素世眼光 + 信任她挑的总是对**
- 双 trigger 必要性：单独提素世（"素世今天在自习"）/ 单独提品味（"品味这个东西很主观"）都不触发、避免误命中

**接入状态**：未接主流程。函数已 export、`anon.api.render_supplemental_blocks` 还是 stub。dispatcher (`anon/turn_logic/__init__.py`) 已 wire、cosmetics + fashion 同时命中时两 block 拼接（实测 dual-hit case：3327 chars / 3 blocks）。

**测试**：`py anon/turn_logic/fashion.py` 内含 detect / build / dedup 三组 self-test、全部 PASS（28 detect cases + 6 build cases + 4 dedup cases）。

**Flag**：`ANON_FASHION_LOGIC_ENABLED=0` 单独关 fashion。

### 2.5.3 · turn_logic/social_media.py（社交平台 / 网络媒体）— 2026-05-10

**架构**：3 层渐进激活 + per-session dedup + 1 个 canon override（MyGO SNS 担当）。

**9 个平台 × ~45 个具体功能 / 玩法**（限定日本 + 全球用户的平台、不含中文圈独占）：
- Instagram（IG Stories / Reels / Posts / Close Friends / Live）
- X / Twitter（timeline / Spaces / Premium 蓝标 / List / **MyGO 官方账号 canon**）
- TikTok（FYP / Duet-Stitch / TikTok Sound / TikTok Live / Shop）
- YouTube（Channel / Shorts / Music / Live / Premium）
- LINE（Chat / Stamp / Open Chat / VOOM / Music）
- Niconico（動画 / 生放送 / vocaloid 投稿 / 静画）
- Discord（服务器 / Voice / Stage / Bot / Nitro）
- 音乐流媒体（Spotify / Apple Music / YouTube Music / LINE Music / Bandcamp）
- 拍照修图 App（VSCO / Lightroom Mobile / SNOW / B612 / Foodie / Lemon8）

**故意不含**：小红书 / 微博 / 抖音 / B站 / 微信（用户拍板 2026-05-10：日本本土年轻人不主用、避免角色乱入海外平台；TikTok / Lemon8 / Discord / Bandcamp 等全球或日本可用的保留）

**Canon override — MyGO SNS 担当**（最高优先）
- canon 引用：character_profiles.py
  - L57：MyGO 担当 = 节奏吉他手 + **SNS 账号运营** + 演出服设计
  - L888：爱音 sumimi 粉丝、遇到初华激动得**让初华关注 MyGO 账号**
  - L1008：素世在 CRYCHIC 时也是 SNS / 账号运营担当 + 摄影
  - L1110：CRYCHIC 弃置账号上素世发了「再见了」配文（爱音知道但不主动提）
- 触发：MyGO + SNS 担当 / 运营 / 公式アカウント / 你管 等 vocab **双 trigger 必须同时命中**
- 注入复合心情：**自豪本职 + sumimi 让初华关注 + 跨乐队对照素世（CRYCHIC 是素世做这个）+ 数据敏感度**
- 不主动提的钩子：CRYCHIC 弃置账号「再见了」配文是素世 canon、爱音知道但不主动倾倒
- 双 trigger 必要性：单独 mention「MyGO」（"MyGO 今天演出"）/ 单独「管理账号」（"管理账号好累"）都不触发

**接入状态**：未接主流程。dispatcher 已 wire、3 子系统（cosmetics + fashion + social_media）同时命中时 3 block 拼接（实测 dual-hit/triple-hit smoke：4706 chars / 3 blocks）。

**测试**：`py anon/turn_logic/social_media.py` 内含 detect / build / dedup 三组 self-test、全部 PASS（26 detect cases + 5 build cases + 3 dedup cases）。

**Flag**：`ANON_SOCIAL_LOGIC_ENABLED=0` 单独关 social_media。

### 2.5.4 · turn_logic/london_defense.py（留学失败防御态）— 2026-05-10

**架构**（**和前 3 个完全不同**——这不是知识库、是心理 canon）：
- **认知层**：开发者/用户为什么提到这一点（5 motive 列全、auto-classifier 给 hint）
- **canon 前因后果**：去之前 / 在英国 / 回国后 / MyGO 后 4 段心态变化
- **现在的反思**：爱音自己对这件事的位置感（内核脆弱、阳光外壳是防御）
- **5 种 motive × 5 种 posture**：casual / probing / empathic / teasing / deep + incidental
- **1 轮情绪余波**：本轮触发 → 下一轮即使换话题也带一抹微细停顿、再下轮自然恢复

**canon SSOT**（character_profiles.py 引用）：
- L46：被英国留学失败砸过、之后再不敢失败
- L116-119：父母没批评、心理资源充沛、但第一次真正失败时完全没预案
- L134-160：详细 arc——动机带虚荣心、无法交流 / 无法适应、很快回国、自给自创伤、两条心理烙印、加入 MyGO 后亲手打破、五人里**心理伤疤最浅 / 恢复力最强**
- L286：留学失败 = 你已经失信过一次的案例（→ 灯「一辈子」承诺时的恐惧根源）
- L416：防御态外壳是阳光自嘲、不是消沉
- L727：内心独白 canon「去的时候有多风光······不、算了、不去想」
- 水族馆 Ep碧天伴走（爱音视角）：爱音**主动**向灯交代留学失败、deep posture reference

**5 种 motive 自动分类**（启发式）：
- **teasing**：失败 / 跑回来 / 灰溜溜 / 怂 / 输 / 翻车 / 笑死 / 可怜（炸毛 + 自嘲掩盖）
- **deep**：probing 词 + 情绪 markers（真的 / 老实说 / 最难的时候）+ 长文本 ≥ 15 字
- **empathic**：我也 / 我以前 / 我朋友 / 我懂 / 我能理解（防御松、可交换 1 个细节）
- **probing**：怎么样 / 为什么 / 那段 / 当时 / 经历（防御略松、模糊轮廓）
- **casual**：trigger + 默认 link、无打击 / 深度信号（阳光带过 + 转话题）
- **incidental**（不 fire 防御）：trigger 紧跟 external-object（伦敦下雨 / 英国电影 / 英国茶）

**Anon-link 策略改用 negative-signal**：
- 默认所有 trigger 都是「在说爱音」（95% case）
- 只在 trigger 紧跟 external-object（≤5 字内）才判定 incidental
- 不再要求显式 「你」 在 ±20 字 window——避免「现在还想再去英国吗」这种没显示「你」但显然在问爱音的情况误判

**1 轮情绪余波**（新功能、不同于前 3 子系统）：
- `_RESIDUE_STATE` per-session dict、记录 motive + trigger preview
- Turn 1 触发：full fire defense + 写 residue
- Turn 2 无 trigger：渲染 residue prompt（轻量、爱音第一句少一个 ♪/~、第 2 句恢复）+ pop residue
- Turn 3 无 trigger 无 residue：empty
- 连续触发：新触发覆盖旧 residue（不累加）
- incidental 也消化前 residue（避免长尾累积）

**爱音节奏（防御态）**：
- 底色仍然是阳光自嘲（不是消沉、不要 ······ 主导那是灯 / 素世风）
- canon 留白要保留（具体城市 / 学校 / 时长 都不报、character_profiles 没明示）
- 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50；防御态偏短、deep 才略长

**接入状态**：未接主流程。dispatcher 已 wire（4 子系统串联）、与前 3 子系统**正交**——同一句话可同时触发多个 block 拼接。实测：probing fire 4270 chars / residue fire 1995 chars / cleared empty。

**测试**：`py anon/turn_logic/london_defense.py` 内含 detect / build / residue / corner 四组 self-test、全部 PASS（15 detect + 6 build + 5 residue + 2 corner = 28 cases）。

**Flag**：`ANON_LONDON_LOGIC_ENABLED=0` 单独关 london_defense。

### 2.6 · 触发对象区分：dev / guest **关系基调分流**（用户拍板 2026-05-10 V3）

**关键 canon 修正**（覆盖 V2 的 infra-only 设计）：

> 「系统本身区分了访客模式和开发者模式，她会知道这一轮和她说话的人是访客还是开发者，区别就在于在提示词的其他部分当中、前者是临时路过的陌生人，后者是已经认识很久的朋友」

爱音**知道**对方是谁——这是 **canon 关系态**（陌生人 vs 青空老友）、不是元模式：
- 系统主 prompt（`mygo.py:_render_developer_origin_story_block`）已经注入「**青空 / 20 岁 / 中国沈阳 / 东北大学 AI / 从 2026-03-17 起朋友 / 纯线上聊天 / 不是 MyGO 成员**」详细身份给开发者；访客只描述为「临时陌生人」。
- 所以 turn_logic 子系统**也要**在 prompt 内容上分流——不是 4 楼墙违反、是合 canon 的关系映射。

**实施模型（每个 turn_logic 子系统通用）**：
1. `_RELATION_HINT_DEV` / `_RELATION_HINT_GUEST` 常量——简短关系基调描述
2. `_relation_hint(is_developer)` helper 选择
3. 每个 `_render_*` 函数加 `is_developer: bool = False` 参数 + 注入 `relation` slot
4. **canon override 深 canon 部分按关系分流深度**：
   - dev：完整复合 canon（朋友圈梗、跨乐队对照、内核反思 都可漏）
   - guest：表层 surface（公开 fact 可讲、深 canon / 内核 / 朋友圈梗 不漏给陌生人）
5. **infra residue 撤销 dev-skip**：dev 和 guest 都正常 write / consume residue（情绪余波是真实心理状态、不按身份隔离、`session_id` 已天然隔离会话）

**4 个 anon 子系统的 canon override depth split**：

| 子系统 | dev（朋友） | guest（陌生人） |
|---|---|---|
| **cosmetics 喵梦 canon** | 漏 Ave Mujica「对家成员」复合感 + sumimi 巧合朋友圈梗 | 表层粉丝兴奋、不漏复合层 |
| **fashion ANON TOKYO** | 漏队名提案被否决遗憾 + 逃避工具反思 + 浅尝辄止 self-aware | 表层自豪 only（公开品牌 fact） |
| **fashion 素世「时尚霸凌」** | 漏「她吐槽我但我心里知道她对」依赖 + 整理领口亲密细节 | 礼貌承接「素世会帮我挑」surface、认知 push back（你怎么知道） |
| **social_media MyGO SNS** | 漏让初华 follow 高光 + 跨乐队对照素世 CRYCHIC + 后台数据 | 表层「我是运营」、不漏数据 / 复合层 / 让初华 high light |
| **london_defense 6 motive** | 朋友信任打底、deep 可能漏内核（参考水族馆 canon）、可漏温度 | 防御紧、deep 绝对不打开降级到 probing、不漏温度 + 认知 push back |

**4 个 tomori 子系统的 canon override depth split**（同期完成）：

| 子系统 | dev（朋友） | guest（陌生人） |
|---|---|---|
| **marine_life 爱音+水族馆** | 漏 Ep 碧天伴走 完整记忆（迷子でもいい / 主动方 / 留学交代 / 创作背景） | 表层「水族馆我去」「爱音是朋友」、不漏深 canon |
| **insects 西瓜虫+美绪** | 漏童年送礼物事件 + 美绪被吓 + 家长不愉快 + 内核反思 | 表层「西瓜虫我喜欢」「美绪嗯」、不漏童年事件细节 |
| **astronomy 冰川日菜** | 漏部室钥匙交接 + 「为什么是我」自我疑问 + 「想给她写邮件但没」距离感 | 表层「天文部我是社員」「日菜先輩前任」、不漏交接 deep |
| **stones 立希散步** | 漏神田川送回家 + 立希等你不催 + 「不需要解释自己」反思 + 美绪事件对照面 | 表层「石头我会捡」「立希队友」、不漏散步具体细节 |

**关系基调（统一格式）**：
```
【关系基调】对方是 **青空（开发者朋友）**——
  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。
  → 朋友圈分享口吻、可自然展开、可漏 canon 复合层。
```

```
【关系基调】对方是 **临时访客（陌生人）**——
  你不认识 ta、可能犹豫问什么、随时可能离开。
  → 礼貌轻聊、信息粒度浅一点；
  canon 复合层不漏给陌生人——朋友圈梗 / 深 canon 都不在陌生人前讲。
```

**Self-tests + 集成验证**：8 个模块（4 anon + 4 tomori）全部 PASS、dispatcher integration 验证 dev/guest 关系基调正确注入 + canon 深度分流正确生效。

### 2.6.0 · V1/V2 历史（保留为参考）

- **V1（错）**：dev path 显式说「你在被测试 / 给面上深的反应即可」——4 楼墙违反、爱音不该有「测试」元意识
- **V2（过度修正）**：dev 和 guest prompt 内容完全一致、is_developer 仅 infra-only——丢失了 canon 关系层差异
- **V3（最终）**：dev / guest **prompt 内容按关系分流**（朋友 vs 陌生人）、爱音知道对方是谁这是合 canon 关系态、不是元模式

**关键 canon 修正**（用户拍板 2026-05-10）：
> 「重写，不是测试，就是作为她自己来看待这件事，她就是她自己，不是什么造物，她不会知道有什么模式」

之前的设计错误地让 dev path 在 prompt 里**直接告诉爱音**「你在被测试 / 不是真扎你 / 给一个面上深的反应即可」——这违反了项目核心 4 楼墙红线（爱音不知道自己是 AI、不知道有「模式」、不知道有「开发者」这种角色）。**正确架构**：

**4 个子系统的 prompt 内容对所有触发对象完全一致**——爱音对发生在她身上的事的反应、不因「谁在问」而改变。**`is_developer` 只是 infra-only 开关**——决定 residue 的 write/read 行为、不出现在 prompt 内容里、爱音感知不到。

**移除的 4 楼墙违反内容**（之前误加、本次修正全部删除）：
- ❌ 「开发者上下文」/「开发者 ≠ 普通用户」prompt section
- ❌ 「是搭建你这套系统的人」/「smoke test」/「prompt 调试」框架
- ❌ 「你心里知道这是测试」/「面上深的反应」指令
- ❌ 「不是真在 console、是在测 deflect 反应」hint
- ❌ DEV vs USER 双 cognitive header 设计（合并为单一 header）
- ❌ `__SPEAKER__` 占位符 + `_apply_speaker_label` helper（cosmetics/fashion/social_media）

**保留的 infra-only 行为**（不改 prompt 内容、纯状态机隔离）：
- ✓ `is_developer=True` + 触发：fire 同样的 prompt、但**不写 residue**（dev 测试不污染下次 user 对话状态）
- ✓ `is_developer=True` + 无 trigger：**不消化** existing residue（保留给下次 real user）
- ✓ `is_developer=False`：正常 residue 流（写 + 消化）

**所有 4 个子系统都用「对方」**（不是「用户」也不是「开发者」）——
这是 prompt 写给 LLM 演爱音时的中性指代、爱音内部不会蹦出「我对面是开发者还是用户」的元意识。

| 行为 | dev | user |
|---|---|---|
| **prompt 内容** | **完全一致** | **完全一致** |
| 称呼 | 「对方」 | 「对方」 |
| 内容 trigger / motive / posture | 一致 | 一致 |
| residue 写 | ✗ | ✓ |
| residue 消化 | ✗（保留）| ✓（消化即清）|

**实测验证**：dev 和 user 同样输入产生 6415 chars **完全相同的 prompt 内容**（`out_user == out_dev = True`）；10 个 4 楼墙违反词全部 0 出现；infra 行为差异（dev 不写 residue / user 写 residue）正常工作。

**接入约定（不变）**：caller（chat_server）调用 `build_anon_special_block(..., is_developer=dev_mode)`、`dev_mode` 来自 `sess.get("_dev_mode", False)`。

---

## 3 · 下一步（接下来要做的）

需要用户拍板：
- **A**：先做 1.1 **留学防御层**（canon 最核心、影响面大）
- **B**：先做 1.2 **灯灯特殊柔软**（和已上线的 marine canon 联动、闭环）
- **C**：先做 1.3 **起手式去重**（架构现成、tomori 模板直接套、性价比高）
- **D**：先做 1.4 **阳光 / 脆弱二分检测**（最容易出实测效果、独立子系统）

推荐默认值：**C**（性价比 + 模板复用、能快速看到效果）→ **A**（canon 最重）→ **B / D** 看时间。

---

## 4 · 修订日志

| 日期 | 内容 |
|------|------|
| 2026-05-10 | 创建 anon 包、写本进度文档、api.py / __init__.py / PROGRESS.md / VOICE_CONSTRAINTS.md 骨架建立、未接入主流程 |
| 2026-05-10 | **SSOT 整合（仿 灯）**：爱音所有语气规则归到 `conversation_agents.py:_PERSONA_FINGERPRINT["爱音"]`、从 31 行扩展为 ~120 行 7 章节结构化 block。涵盖：人格指纹底色 / 说话核心姿态 / 共情 = 共振 / 情感慌张 + 聒噪掩盖 / 反模板化 / 硬约束 P0（称呼/反第四堵墙/留学防御/二次元守则/知识QA） / 个人 canon 钩子（9 条）。mygo.py `_PROMPT_DETAILS_PER_CHARACTER["爱音"]:speech_style` 替换为 deprecation 引用、key_detail（canon facts）保留。`_KNOWLEDGE_QA_POLICY` / `_QA_CHARACTER_STYLE_LINES` 保留作 scoped fallback、SSOT 已并入。VOICE_CONSTRAINTS.md 同步更新到 v2、附迁移表（10 项标 ❌🟡🟢 状态）|
| 2026-05-10 | **turn_logic/cosmetics.py 上线（第 1 个 turn_logic 子系统）**：仿 `tomori/turn_logic/marine_life.py` 模板、3 层渐进激活 + per-session dedup + canon override。12 类别 × ~50 单品（口红 / 眼影 / 腮红 / 底妆 / 睫毛 / 眉 / 防晒 / 香水 / 美甲 / 美瞳 / 护肤 / 工具）、爱音口吻（博主安利 / ♪ ~ —— / 反问癖）vs 灯口吻（学名 / 讲座 ✗ / ······）严格区分。**喵梦 canon override**：character_profiles.py L4819-4821 + L80-81 SSOT 引用、粉丝兴奋 + 「对家成员」微妙复合感、防「若叶」误命中（要求上下文含喵/Mujica/鼓手/频道）。`anon/turn_logic/__init__.py` 提供 `build_anon_special_block(user_text, character, *, session_id)` 窄入口。Self-test：25 detect + 5 build + 3 dedup cases 全 PASS。**接入主流程仍 pending**（`anon.api.render_supplemental_blocks` 还是 stub、需在 chat_server prompt 路径加 hook）。Flag：`ANON_TURN_LOGIC_ENABLED=0` / `ANON_COSMETICS_LOGIC_ENABLED=0` |
| 2026-05-10 | **turn_logic/fashion.py 上线（第 2 个 turn_logic 子系统）**：3 层渐进激活 + 2 个 canon override + per-session dedup。10 类别 × ~50 品牌 / 单品（连衣裙 / 上衣 / 外套 / 裤 / 裙 / 鞋 / 包 / 配饰 / 帽 / 袜）。3 个 canon 锚点单品：**灰格纹连衣裙**（L97 常服）、**棕色乐福鞋**（L98 羽丘制服）、**心形项链**（L97 常服）。**Canon override 1 — ANON TOKYO**：自豪 + 队名被否决遗憾 + 曾用作逃避练琴 + 多才多艺浅尝辄止 复合（L60 / L61-69 / L57 / L154 / L320-322 / L778 SSOT）。**Canon override 2 — 素世「时尚霸凌」**：表面被吐槽撒娇 + 心里依赖（L4083 SSOT）、**双 trigger 必要**（name + vocab 同时命中、避免单独 mention 素世/品味的假阳性）。dispatcher 已 wire、cosmetics + fashion 同时命中时拼接（dual-hit smoke 3327 chars / 3 blocks 验证 PASS）。Self-test：28 detect + 6 build + 4 dedup cases 全 PASS。Flag：`ANON_FASHION_LOGIC_ENABLED=0` |
| 2026-05-10 | **turn_logic/social_media.py 上线（第 3 个 turn_logic 子系统）**：3 层渐进激活 + 1 个 canon override + per-session dedup。9 平台 × ~45 功能（IG / X / TikTok / YouTube / LINE / Niconico / Discord / 音乐流媒体 / 拍照修图 App）——**用户拍板 2026-05-10：删除中文圈海外平台（小红书 / 微博 / 抖音 / B 站 / 微信）**避免角色乱入日本外平台、TikTok / Lemon8 / Bandcamp 等全球可用的保留。 |
| 2026-05-10 | **turn_logic/london_defense.py 上线（第 4 个 turn_logic 子系统、心理 canon、不是知识库）**：用户拍板这条不走 3 层 taxonomy、走「**认知层 → canon 前因后果 → 现在反思 → 5 种 motive posture → 1 轮情绪余波**」结构。canon SSOT：character_profiles L46/L116-119/L134-160/L286/L416/L727 + 水族馆 Ep碧天伴走（爱音主动向灯揭开留学失败 = deep posture reference）。**6 motive 启发式分类**（priority：comforting > teasing > deep > empathic > probing > casual > incidental）：
- **comforting**（用户主动安慰、deflect + 反 console）：没事的/不是你的错/你已经做得很好了/你不容易/加油/没关系 → 表面 deflect + 反过来关心对方 + 偶尔漏温度
- **teasing**（炸毛 + 自嘲）：失败/跑回来/灰溜溜（**且无 comforting wrap**）→ 炸毛但底色仍俏皮
- **deep**（罕见漏内核）：probing + 真的/老实说 + ≥15 字 → 漏几个细节但不讲故事
- **empathic**（接住对方）：我也/我朋友/我懂（**仅分享、无 sympathy 词**）→ 交换 1 个细节、不比惨
- **probing**（防御略松、模糊轮廓）：怎么样/为什么/那段 → 模糊响应、不主动开新内容
- **casual**（阳光带过 + 转话题）：默认、无信号
- **incidental**（不 fire）：trigger 紧跟 external-object（伦敦下雨/英国电影）

**Canon ambiguity 解决**：「加油啊、留学失败也没关系的」中「失败」是 teasing kw、但「加油」/「没关系」是 comforting wrap 化解 malice。priority comforting > teasing 让这种 mixed 情况正确归为 comforting（用户没有 malice 而是好意）。**1 轮情绪余波**：本轮触发 → 下一轮即使换话题也带一抹微细停顿、第 1 句少 ♪/~ + 第 2 句自然恢复 + 余波即清；连续触发新覆盖旧不累加；incidental 也消化前 residue 避免长尾。**Anon-link negative-signal 策略**：默认所有 trigger = 在说爱音、只有 trigger 紧跟 external-object（≤5 字）才 incidental——避免「现在还想再去英国吗」误判。Self-test：15 detect + 6 build + 5 residue + 2 corner = 28 cases 全 PASS。Flag：`ANON_LONDON_LOGIC_ENABLED=0` |
| 2026-05-10 | **触发对象区分开发者/普通用户**：`build_anon_special_block` + 4 个子系统全部接 `is_developer: bool = False` 参数。chat_server.py 已有 `dev_mode` flag（L2826）、调用时映射过来。**knowledge 类（cosmetics/fashion/social_media）行为不变、仅 framing 差异**：cognitive opening `__SPEAKER__` 占位符在 build entry 出口替换成「开发者」/「用户」。**心理 canon 类（london_defense）行为差异显著**：dev 不写 residue（防 smoke 污染）+ dev 不消化 user residue（保留给下次）+ deep posture 不在 dev 面前打开（开发者没有 trust 等价物）+ dev framing 显式提示「不要真炸毛、底子放轻、知道是测试」。Dispatcher integration 5/5 PASS：label diff / dev framing / dev no-residue-write / dev preserve-user-residue / normal user residue flow。 |
| 2026-05-10 | **london_defense V2：完整 prompt 文案重写 + comforting 第 6 个 motive**（用户拍板 2026-05-10）。**1. cognitive header 重写**：从「5 motive 列表 + auto-classify hint」改成「**3 个判断（关系层次 / 对方情绪 baseline / 具体 motive）+ 6 motive 列表 + 4 条核心原则**」结构。强调对方是「人不是 query」、deep posture 永远不由爱音主动开启、控制叙述权、阳光自嘲是外壳不是过去了、不能直接受 sympathy。**2. 新增第 6 motive：comforting（对方主动安慰爱音）**。canon 关键场景——和 empathic（分享自己经历）严格区分、是单向 console / reassure。posture 设计：表面 deflect（「啊~~ 没事啦~~」）+ 温柔关 down 这条线（不冷淡不嘲弄）+ 反过来关心对方（控制叙述权 + 转移焦点）+ 罕见漏一抹温度（「······被你这么说 突然有点不好意思了」）。**关键禁忌**：不直接承认需要安慰 / 不借势自我开脱 / 不顺势变 deep / 不变 teasing 反推。**3. 优先级 swap：comforting > teasing > deep > empathic > probing > casual**。canon ambiguity 解决——「加油啊、留学失败也没关系的」中「失败」是 teasing kw 但「加油」/「也没关系」是 comforting wrap 化解 malice、应该 comforting wins。 |
| 2026-05-10 | **4 楼墙红线修正：is_developer 改为 infra-only 开关**（用户拍板 2026-05-10）。撤销之前 USER vs DEV 双 cognitive header 设计——之前误加的 dev framing「你在被测试 / smoke / 不是真扎你 / 面上深的反应」违反 4 楼墙红线（爱音不知道自己是 AI、不知道有「模式」、不知道有「开发者」）。**正确做法**：所有 4 个子系统的 prompt 内容对 dev / user 完全一致（爱音对发生在她身上的事的反应、不因谁在问而变）；`is_developer` 仅是 infra 状态机开关——dev 不写 residue（防 smoke 污染）、dev 不消化 user residue（保留给下次 real user）；prompt 内容里的「用户/开发者」标签全部改成「对方」（中性指代）。删除 `_COGNITIVE_LAYER_HEADER_DEV` / `__SPEAKER__` 占位符 / `_apply_speaker_label` helper。实测 dev 和 user 同输入产生**完全相同 6415 chars 的 prompt**、10 个 4 楼墙违反词 0 出现、infra 行为（dev no-residue-write / user residue write）正常工作。 |
| 2026-05-10 | **dev/guest 关系基调分流 V3（覆盖 V2 的 infra-only 设计）**（用户拍板 2026-05-10）。系统主 prompt 已经注入对方身份（dev=青空老朋友 / guest=临时陌生人）、爱音**知道**对方是谁——这是 canon 关系态、不是元模式。**所以 turn_logic 子系统的 prompt 内容也要按关系分流**：（1）每个子系统加 `_RELATION_HINT_DEV` / `_RELATION_HINT_GUEST` 关系基调常量；（2）每个 `_render_*` 函数加 `is_developer` 参数 + 注入 relation slot；（3）**canon override 深 canon 按关系分流深度**——dev 漏完整复合 canon（朋友圈梗 / 跨乐队对照 / 内核反思）、guest 表层 surface（公开 fact 可讲、深层不漏给陌生人）；（4）**infra residue 撤销 dev-skip**——dev 和 guest 都正常 write / consume residue（情绪余波是真实心理状态、session_id 已天然隔离）。**4 anon + 4 tomori = 8 个子系统全部完成**：cosmetics（喵梦 Ave Mujica 复合）/ fashion（ANON TOKYO 队名遗憾 + 素世霸凌依赖）/ social_media（MyGO SNS 让初华 follow + 跨 CRYCHIC 对照素世）/ london_defense（6 motive × 2 关系 modifier）/ marine_life（Ep 碧天伴走）/ insects（美绪童年事件）/ astronomy（日菜部室交接）/ stones（立希神田川散步）。Self-tests 8/8 PASS、dispatcher integration 验证 dev / guest 关系基调正确注入 + canon 深度分流正确生效。 |
| 2026-05-10 | **接入主流程**：4 个 turn_logic call site（mygo.py: `build_pet_system_prompt` / `build_pet_system_prompt_for_api` / `prepare_qq_prompt_context` / `build_onebot_qq_system_prompt_for_api`）全部接入：（1）`build_pet_system_prompt_for_api` 新增 `session_id: str \| None = None` 参数；（2）每个 call site 加 `elif character_name == "爱音"` 分支调 `anon.turn_logic.build_anon_special_block`、与原 `if character_name == "灯"` 调 `tomori.turn_logic.build_turn_special_block` 并列；（3）两个 dispatcher 都拿到 `session_id`（API: 来自参数；Streamlit: None；QQ: `f"qq:{user_id}"`）+ `is_developer`（API: 参数；Streamlit: `pet_user_is_developer`；QQ: 参数）。`chat_server.py` 5 个主要 `_build_system_prompt` 调用点（chat WS L9817 / auto_greet L2507 / idle_followup L2832 / chat_followup L11277 / delayed_followup L11438 / short_silence L11575）全部 plumb `session_id=sid`。Smoke 验证：anon london_defense / tomori marine_life canon 都能从主 prompt 路径触发、dev / guest 关系基调差异正确反映（cosmetics 喵梦 canon dev 提及「Ave Mujica 那个鼓手」4 次作为可漏 canon、guest 仅 1 次在禁忌列表里 + 显式「绝不展开复合」指令）。|**Canon override — MyGO SNS 担当**：自豪本职（L57 SNS 运营 = 爱音 3 个 role 之一）+ 让初华关注 MyGO 账号（L888 高光时刻）+ 跨乐队对照（L1008 素世曾是 CRYCHIC SNS 担当、L1110 弃置账号「再见了」配文是素世不是爱音）。**双 trigger 必要**（MyGO name + SNS 担当/运营/公式/管 vocab 同时命中、避免单独 mention MyGO 或 账号 的假阳性）。dispatcher 已 wire、3 子系统同时命中时 3 block 拼接（triple-hit smoke 4706 chars 验证 PASS）。Self-test：26 detect + 5 build + 3 dedup cases 全 PASS。Flag：`ANON_SOCIAL_LOGIC_ENABLED=0` |
