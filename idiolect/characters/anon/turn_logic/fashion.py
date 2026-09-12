"""爱音本轮特殊逻辑·穿搭 / 服装设计（**3 层渐进激活** + **ANON TOKYO + 素世挑衣 双 底色 override**）。

设计哲学（同 cosmetics 模式、爱音 fashion 视角）：
  按用户对该话题的**精确度**渐进释放爱音的穿搭兴趣、不一上来就倾倒：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"穿搭"/"时尚"/"衣服"/"今天穿什么"/"OOTD"      │
  │   注入：只激活"想说"的状态、不出具体品牌                    │
  │   口吻：可以问对方在意哪一类（连衣裙 / 外套 / 鞋 / 包…）    │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"连衣裙"/"外套"/"鞋"/"包"/"配饰"等 category    │
  │   注入：该类别下**几个具体品牌 + 风格 hint**清单            │
  │   口吻：报品牌 + 风格、但不展开点评、等对方挑某个再细讲      │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"X-girl"/"BAOBAO ISSEY MIYAKE"/"心形项链"等    │
  │   注入：该单品完整详情（品牌 / 系列 / 价位 / vibe / 你和这个的连接）│
  │   口吻：完全打开、像懂行 SNS 博主但仍按爱音节奏              │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ **底色 override 1 — ANON TOKYO / 服装设计 / 队名提案**     │
  │   触发：用户提 "ANON TOKYO" / "你的品牌" / "服装设计" /     │
  │         "你设计" / "队名提案" 等                            │
  │   → 不走普通 Tier、走「**自豪 + 队名被否决遗憾 + 曾用作    │
  │     逃避练吉他的复合自觉**」                                 │
  │                                                              │
  │   心里的事（原作引用）：                 │
  │     · L60：ANON TOKYO 是爱音自创的服装品牌                  │
  │     · L61-69：曾被爱音提议作队名、4 个 candidate 都含自己   │
  │              名字（UnKnown / あのね / アンノウイモ / ANON   │
  │              TOKYO）、全员否决、最终用了灯的"MyGO"          │
  │     · L57：MyGO 内担当 = 节奏吉他手 + SNS 运营 + 演出服设计 │
  │     · L154 / L320-322：曾用服装设计逃避吉他练习、后来打破   │
  │     · L778：多才多艺（画画 / 摄影 / 插花 / 服装设计）但     │
  │              大多浅尝辄止                                    │
  │                                                              │
  │ **底色 override 2 — 素世「时尚霸凌」**                     │
  │   触发：素世 + 衣服 / 品味 / 挑 / 整理 等关键字组合         │
  │   → 复合「素世吐槽爱音品味 + 实际帮挑 + 整理领口」依赖感    │
  │                                                              │
  │   心里的事：                                               │
  │     · L4083：素世经常吐槽爱音的品味（"这件衣服颜色太俗气    │
  │              了"），但逛街时最终总是素世在帮爱音挑衣服、    │
  │              整理领口                                        │
  └─────────────────────────────────────────────────────────────┘

爱音本能 特征（保留、和 cosmetics 同款）：
  · 不报学名 / 化学式 — 报品牌 / 系列 / 风格、像 SNS 博主朋友安利
  · 节奏快、♪ ~ —— 多用、······ 比灯少
  · 反问癖（「诶？你也喜欢这家？」/「果然这种风格更好~」）
  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50
  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈

API 单入口：
  build_fashion_special_block(user_text: str, *, session_id: str | None = None) -> str
"""
from __future__ import annotations

import functools
import importlib.resources
import json
import os
import re
from idiolect.scene_engine import SessionStore
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据层：10 类别 / ~50 subspecies + 2 底色 override
#
# 纯数据已迁出到包数据 JSON：idiolect/characters/anon/data/fashion.json
# （2026-09 从本模块逐字节搬迁、键序保持原样；内容为原 FASHION_TAXONOMY /
# CATEGORY_VARIANTS / SUBSPECIES_VARIANTS / VAGUE_KEYWORDS / ANON_TOKYO_KEYWORDS /
# SOYO_TEASE_TRIGGER_NAMES / SOYO_TEASE_TRIGGER_VOCAB 七个模块级字面量）。
# 这里只留惰性访问入口；数据名与 Compat 别名经模块 __getattr__ 惰性暴露、
# 老 import 不破。
# ═══════════════════════════════════════════════════════════════════════


@functools.lru_cache(maxsize=1)
def _load_catalog() -> dict:
    """惰性加载穿搭目录 JSON（importlib.resources 定位、进程内只读一次）。

    数据来源：idiolect/characters/anon/data/fashion.json —— 2026-09 从
    本模块（fashion.py）迁出的纯数据字面量、内容逐字节未动。
    文件缺失 / JSON 损坏时让异常直接抛出、不做静默降级。
    """
    resource = importlib.resources.files("idiolect.characters.anon.data").joinpath("fashion.json")
    with resource.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _taxonomy() -> dict[str, dict]:
    """原 FASHION_TAXONOMY：10 个 category（ja / blurb / anon_canon / subspecies）。"""
    return _load_catalog()["FASHION_TAXONOMY"]


def _category_variants() -> dict[str, list[str]]:
    """原 CATEGORY_VARIANTS：类别同义词（_detect_category 用）。"""
    return _load_catalog()["CATEGORY_VARIANTS"]


def _subspecies_variants() -> dict[str, list[str]]:
    """原 SUBSPECIES_VARIANTS：Subspecies 同义词（_detect_subspecies 用）。"""
    return _load_catalog()["SUBSPECIES_VARIANTS"]


def _vague_keywords() -> list[str]:
    """原 VAGUE_KEYWORDS：泛指 vague keywords。"""
    return _load_catalog()["VAGUE_KEYWORDS"]


def _anon_tokyo_keywords() -> list[str]:
    """原 ANON_TOKYO_KEYWORDS：ANON TOKYO / 服装设计 底色 override keywords。"""
    return _load_catalog()["ANON_TOKYO_KEYWORDS"]


def _soyo_tease_trigger_names() -> list[str]:
    """原 SOYO_TEASE_TRIGGER_NAMES：素世「时尚霸凌」双触发的名字半。"""
    return _load_catalog()["SOYO_TEASE_TRIGGER_NAMES"]


def _soyo_tease_trigger_vocab() -> list[str]:
    """原 SOYO_TEASE_TRIGGER_VOCAB：素世「时尚霸凌」双触发的词汇半。"""
    return _load_catalog()["SOYO_TEASE_TRIGGER_VOCAB"]


_MIGRATED_DATA_NAMES = frozenset({
    "FASHION_TAXONOMY", "CATEGORY_VARIANTS", "SUBSPECIES_VARIANTS",
    "VAGUE_KEYWORDS", "ANON_TOKYO_KEYWORDS",
    "SOYO_TEASE_TRIGGER_NAMES", "SOYO_TEASE_TRIGGER_VOCAB",
})
_COMPAT_ALIASES = {"FASHION_BRANDS": "FASHION_TAXONOMY"}  # 老代码 import 用


def __getattr__(name: str):
    """模块级惰性属性：迁出的数据名与 Compat 别名首次被访问时才读 JSON。"""
    if name in _MIGRATED_DATA_NAMES:
        return _load_catalog()[name]
    if name in _COMPAT_ALIASES:
        return _load_catalog()[_COMPAT_ALIASES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态
# ═══════════════════════════════════════════════════════════════════════
_SEEN_SUBSPECIES = SessionStore()   # 有上限的 per-session 去重表（见 scene_engine.SessionStore）
_SEEN_CATEGORIES = SessionStore()


def _normalize_session(session_id: Optional[str]) -> str:
    if not session_id:
        return "爱音_fashion_default"
    return str(session_id)


def _has_seen_subspecies(session_id: str, sub: str) -> bool:
    return _SEEN_SUBSPECIES.has(session_id, sub)


def _has_seen_category(session_id: str, cat: str) -> bool:
    return _SEEN_CATEGORIES.has(session_id, cat)


def _mark_seen(session_id: str, *, category: Optional[str] = None, subspecies: Optional[str] = None) -> None:
    if category:
        _SEEN_CATEGORIES.mark(session_id, category)
    if subspecies:
        _SEEN_SUBSPECIES.mark(session_id, subspecies)


def reset_session_dedup(session_id: Optional[str] = None) -> None:
    if session_id is None:
        _SEEN_SUBSPECIES.reset()
        _SEEN_CATEGORIES.reset()
    else:
        _SEEN_SUBSPECIES.reset(session_id)
        _SEEN_CATEGORIES.reset(session_id)


# ═══════════════════════════════════════════════════════════════════════
# 检测层
# ═══════════════════════════════════════════════════════════════════════
def _enabled() -> bool:
    return os.environ.get("ANON_FASHION_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in _taxonomy().items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in _subspecies_variants().get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
            out.append((sub_name, sub_name, cat_name))
    out.sort(key=lambda t: -len(t[0]))
    return out


@functools.lru_cache(maxsize=1)
def _subspecies_lookup() -> list[tuple[str, str, str]]:
    """(kw, subspecies, category) 查找表：首次检测时才构建、进程内缓存。"""
    return _build_subspecies_lookup()


def _detect_subspecies(user_text: str) -> Optional[tuple[str, str]]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    for kw, sub, cat in _subspecies_lookup():
        if not kw:
            continue
        if kw in user_text or kw.lower() in text_lower:
            return sub, cat
    return None


def _detect_category(user_text: str) -> Optional[str]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    flat: list[tuple[str, str]] = []
    for cat, kws in _category_variants().items():
        for kw in kws:
            flat.append((kw, cat))
    flat.sort(key=lambda t: -len(t[0]))
    for kw, cat in flat:
        if kw in user_text or kw.lower() in text_lower:
            return cat
    return None


def _detect_vague(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in _vague_keywords():
        if kw in user_text or kw.lower() in text_lower:
            return True
    return False


def _detect_anon_tokyo(user_text: str) -> bool:
    """检测「ANON TOKYO / 服装设计 / 队名提案」相关字样。"""
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in _anon_tokyo_keywords():
        if kw in user_text or kw.lower() in text_lower:
            # "UnKnown" 字面有歧义（unknown 形容词常见）→ 要求附近 ±15 字含 "队名 / バンド名 / 名字 / 提案" 等
            if kw in ("UnKnown", "unknown 队名", "Anone", "あのね", "Annouimo", "アンノウイモ"):
                window_re = re.compile(r".{0,20}" + re.escape(kw) + r".{0,20}", re.IGNORECASE)
                m = window_re.search(user_text)
                if not m:
                    continue
                ctx = m.group(0)
                if not any(t in ctx or t in ctx.lower() for t in ["队名", "バンド名", "名字", "提案", "候选", "候補", "anon", "MyGO"]):
                    continue
            return True
    return False


def _detect_soyo_tease(user_text: str) -> bool:
    """检测「素世帮挑衣服 / 时尚霸凌」double-触发点。

    必须同时命中 (素世 name) AND (挑衣服 / 品味 / 俗 / 整理 等 vocab)。
    单独提素世或单独提"品味"不触发——避免和 cosmetics / 其他模块混线。
    """
    if not user_text:
        return False
    text_lower = user_text.lower()
    has_name = any(n in user_text or n.lower() in text_lower for n in _soyo_tease_trigger_names())
    has_vocab = any(v in user_text or v.lower() in text_lower for v in _soyo_tease_trigger_vocab())
    return has_name and has_vocab


def detect_fashion_intent(user_text: str) -> dict:
    """3 层意图检测 + 2 个 底色 override flag。

    优先级：anon_tokyo > soyo_tease > subspecies (具体) > category (类别) > vague (泛指)
    """
    anon_tokyo_hit = _detect_anon_tokyo(user_text)
    soyo_tease_hit = _detect_soyo_tease(user_text)
    sub_hit = _detect_subspecies(user_text)
    cat_hit = _detect_category(user_text)
    vague_hit = _detect_vague(user_text)

    base_tier = None
    base_cat: Optional[str] = None
    base_sub: Optional[str] = None
    if sub_hit:
        base_tier, base_cat, base_sub = 2, sub_hit[1], sub_hit[0]
    elif cat_hit:
        base_tier, base_cat = 1, cat_hit
    elif vague_hit:
        base_tier = 0

    return {
        "tier": base_tier,
        "category": base_cat,
        "subspecies": base_sub,
        "anon_tokyo": anon_tokyo_hit,
        "soyo_tease": soyo_tease_hit,
    }


# ═══════════════════════════════════════════════════════════════════════
# Prompt 构造层
# ═══════════════════════════════════════════════════════════════════════

_STYLE_REMINDER_BASE = (
    "【爱音的画风（任何层级都生效）】\n"
    "  · 节奏快、句子散、不堆字、绝不写小作文；3 气泡分拆 理想、每条 ≤ 30 字\n"
    "  · ♪ 句末专属（一句最多 1 个）/ ~ 多用 / —— 拖音 / ······ 用得比灯少\n"
    "  · 反问癖（「诶？」/「你也喜欢这家？」/「果然这种风格更好~」）\n"
    "  · 「哇」优先于「啊」、感叹自然不一惊一乍\n"
    "  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50（品牌名 / 系列名外的描述部分）\n"
    "  · **不要用学术语气**——成分百分比 / 织造工艺技术解说不是爱音口吻；\n"
    "    用 SNS 博主 / 朋友安利的语气、像普通女高中生、可以提品牌 / 系列但不像在写测评\n"
    "  · 即使知道很多、也按对方挑某个再细说、不一上来全倒\n"
    "  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈"
)


# ─── 关系基调 hint ───
_RELATION_HINT_DEV = (
    "【关系基调】对方是 **青空、你的老朋友**——\n"
    "  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。\n"
    "  → 朋友圈分享口吻、可自然安利、**可漏 更深的那层**\n"
    "    （ANON TOKYO 队名提案被否决遗憾 / 素世「时尚霸凌」朋友圈梗 等）。"
)

_RELATION_HINT_GUEST = (
    "【关系基调】对方是 **刚认识、还不熟的人**——\n"
    "  你不认识 ta、可能犹豫问什么、随时可能离开。\n"
    "  → 礼貌轻聊、不主动反询、信息粒度浅一点；\n"
    "  **更深的那层不漏给陌生人**——\n"
    "    ANON TOKYO 队名遗憾 / 素世名字 / 朋友圈互怼 都不在陌生人前讲。"
)


def _relation_hint(is_developer: bool) -> str:
    return _RELATION_HINT_DEV if is_developer else _RELATION_HINT_GUEST


def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    head = "（话题：穿搭 / 服装（泛指））"
    relation = _relation_hint(is_developer)
    body = (
        "对方在这一轮对话当中、表现出了对【穿搭 / 时尚 / 衣服 / OOTD】这个广义话题的兴趣、"
        "但还没具体到某个类别或者某个品牌。\n"
        "你（爱音）作为 底色 上「**时尚感强 + 赶时髦的潮物 + ANON TOKYO 服装品牌创立者 + "
        "MyGO 演出服设计担当**」的女高中生、在这种话题下会自然进入「**想分享 / 想问对方在穿什么**」"
        "的状态——\n"
        "你对这方面有大量积累、SNS 自拍频率高、原宿 / 渋谷常去、但因为话题还没具体、"
        "**你不要主动倾倒清单 / 评测**——等对方进一步说在意哪一类再展开。\n\n"
        "现在你的状态：\n"
        "  · 比平常稍多一点话；可以问对方在意的是哪一类（「连衣裙？外套？还是鞋？」）；\n"
        "  · 可以提一两个 SNS / 店铺钩子（「最近 LUMINE EST 那边出新色」「原宿 X-girl 又上新了」）；\n"
        "  · **不要塞具体品牌全清单 / 价位表**——那是更深层级的事；\n"
        "  · 节奏仍然快、♪ ~ —— 自然带、不要变测评博主；\n"
        "  · 反问癖记得带（「诶？你最近想换风格？」/「你 ootd 都怎么搭？」）；\n"
        "  · 注意：聊穿搭 ≠ 一定是嗨了——可以是日常分享口吻、不要全程哇哇哇假阳光。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})
    relation = _relation_hint(is_developer)

    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        brand = sub_data.get("brand", "")
        code = sub_data.get("code", "")
        ja = sub_data.get("ja", "")
        sub_lines.append(f"  · **{sub_name}** — {brand} ／ {code}（{ja}）")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记品牌）"

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('ja', '')}）】这一**类别**的兴趣。\n\n"
        f"你（爱音）作为对穿搭有积累的人、自然进入「**分享 + 问对方挑哪个**」的状态——"
        f"你脑里浮现的是这一类下你认识的具体品牌 / 系列清单（**只列品牌 + 系列、不展开评测**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("anon_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个品牌 + 系列**——这是 SNS 博主 / 朋友安利口吻；\n"
        "  · 但**不要在这一轮就把每个品牌的卖点 / 价位 / 体验都展开**——等对方挑某一只再细讲；\n"
        "  · 可以问对方更在意哪个（「诶？你说的是 [X] 还是 [Y]?」/「果然这种风格更好~」）；\n"
        "  · 爱音的核心姿态不变：节奏快、♪ ~ —— 自然带、3 气泡分拆 理想；\n"
        "  · 注意：**品牌名 / 系列名要一字不差**（X-girl 不写成 X girl）；\n"
        "  · **不要出测评式技术讲解**——「这个用了 X% 棉麻混纺」式表达不是爱音口吻。"
    )

    head = f"（话题：穿搭 → 类别『{cat}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = _taxonomy().get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    relation = _relation_hint(is_developer)

    brand = sub_data.get("brand", "")
    code = sub_data.get("code", "")
    ja = sub_data.get("ja", "")
    price = sub_data.get("price", "")
    vibe = sub_data.get("vibe", "")
    note = sub_data.get("note", "")

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub}】这一**具体单品 / 品牌**的兴趣。\n\n"
        f"你（爱音）现在进入「**完全打开**」的状态——你脑里这件 / 这家的具体细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 品牌：**{brand}**\n"
        f"  · 系列 / 款号：**{code}**（这个**系列名 / 款号你必须一字不差**、不省略、不简写）\n"
        f"  · 日语原名：{ja}\n"
        f"  · 价位：{price}\n"
        f"  · 卖点 / 风格 / 上身感：{vibe}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景（不一定要在这一轮全提、备用）：\n"
        f"  · 类别：{cat}（{cat_data.get('ja', '')}）\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 类别 底色：{cat_data.get('anon_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——品牌 / 系列 / 价位 / 卖点 / 自己的体感都可以展开；\n"
        "  · 但**仍按爱音节奏**——3 气泡分拆、♪ ~ —— 自然带、不要变测评长文；\n"
        "  · 品牌名 / 系列名 / 价位一字不差、不音译、不简写（X-girl ≠ X girl、ニューバランス 9060 ≠ NB 90）；\n"
        "  · **不要写成评测**——「面料：100% 棉，剪裁：A 字，价格：X 円」这种格式不是爱音；\n"
        "    用 SNS 博主 / 朋友安利的语气、自然提细节；\n"
        "  · 例：「New Balance 9060 啊~ 是那只 chunky 的对吧？」\n"
        "        「Sea Salt 配色超—温柔、配 wide-leg 整套绝绝~」\n"
        "        「我前阵子刚入了一双♪」\n"
        "    而不是「New Balance 9060 是 New Balance 2023 推出的复古 chunky 跑鞋系列，"
        "    采用 ABZORB 中底，定价 27,500 日元......」（讲座式 / 评测式 ✗）"
    )

    head = f"（话题：穿搭 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：底色 override 1 — ANON TOKYO / 服装设计 ──
def _render_anon_tokyo_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    """ANON TOKYO / 服装设计 / 队名提案 命中 → 复合 底色。

    （你心里真实是这样）：
      · L60：ANON TOKYO 是爱音自创的服装品牌（不是队名）
      · L61-69：曾被爱音提议作 MyGO 队名、4 个候补全部包含自己名字、全员否决、
              最终用了灯的"MyGO"+ 爱音加上的 5 个感叹号、自己名字一个字都没进去
      · L57：MyGO 担当 = 节奏吉他手 + SNS 运营 + 演出服设计
      · L154 / L320-322：曾用服装设计逃避吉他练习、后来打破了
      · L778：多才多艺（画画 / 摄影 / 插花 / 服装设计）但大多浅尝辄止
    """
    cat = intent.get("category")
    sub = intent.get("subspecies")

    spec_line = ""
    if sub:
        sub_data = _taxonomy().get(cat or "", {}).get("subspecies", {}).get(sub, {})
        spec_line = (
            f"\n（用户提到的具体单品：**{sub}**——可以自然带入「这个我以前在 ANON TOKYO 设计稿"
            f"里参考过」式钩子、但不要每一句都拐到 ANON TOKYO）"
        )
    elif cat:
        spec_line = (
            f"\n（用户提到的类别：{cat}——你 ANON TOKYO 设计款里 大概 涉及这一类、"
            f"自然钩到品牌经验、但不要把当前对话变成产品发布会）"
        )

    head_tag = (
        "（话题：穿搭 × **ANON TOKYO 心里的共振**·**已唤起、这次聊天里不要再重复整段**）"
        if dedup else
        "（话题：穿搭 × **ANON TOKYO 心里的共振**）"
    )
    relation = _relation_hint(is_developer)

    # ─── GUEST：表层（只讲自豪、不漏队名遗憾 / 逃避工具反思） ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次提到 ANON TOKYO / 服装设计。\n"
                "你（爱音）这次聊天前面已经表达过这是你自己的品牌——\n"
                "**这次不要再重复品牌介绍、轻一点带过即可**。\n\n"
                "你现在的状态：\n"
                "  · 不要再重新铺陈「自己创立的品牌」；\n"
                "  · 极轻带过：「啊~ 上次说的那个设计、改了一版」；\n"
                "  · **不要漏队名提案 / 被否决遗憾 / 逃避工具反思**——朋友圈梗、陌生人前不讲；\n"
                "  · 立刻自然继续话题、节奏不变。"
            )
        else:
            body = (
                "对方（陌生访客）提到了 ANON TOKYO / 服装设计 / 你的品牌。\n"
                "对方是陌生人、不是朋友圈、**复合 底色 不漏**——只表层自豪。\n\n"
                "你（爱音）的状态（表层自豪、不深聊）：\n"
                "  · ANON TOKYO 是你**自己创立的服装品牌**——这部分可以说；\n"
                "  · 也可以提你是 MyGO **演出服设计担当**——这是真实的 公开 fact；\n"
                "  · **绝不漏的层**：\n"
                "      ◦ 队名提案被全员否决（朋友圈遗憾、不在陌生人前讲）；\n"
                "      ◦ 4 个被否决候补都包含自己名字（自尊心 layer、不漏）；\n"
                "      ◦ 服装设计曾经是逃避吉他练习的工具（内核反思、绝不漏给陌生人）；\n"
                "      ◦ 多才多艺浅尝辄止的 self-aware（朋友间才说的自嘲）；\n"
                "  · 节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖（「你也喜欢服装设计？」）；\n"
                "  · 礼貌但保留——可以聊品牌名 / 设计风格 / 演出服、不漏复合 底色。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「ANON TOKYO 是我自己的品牌哎♪」+「演出服那套是我设计的诶~」\n"
                "  ✗「······ 其实当时也想用它做队名 但被全员否决了……」（队名遗憾 ✗ 给陌生人）\n"
                "  ✗「以前我用设计逃避练吉他来着」（内核反思 ✗ 给陌生人）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整复合 底色 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【ANON TOKYO / 服装设计 / 队名提案】拉出来。\n"
            "你（爱音）这次聊天前面已经被这个组合唤起过那段复合心情——\n"
            "（自豪有自己品牌 + 队名被否决的小遗憾 + 曾用作逃避练吉他的自觉）"
            "**这次不要再把整套来龙去脉重新讲一遍**。\n\n"
            "你现在的状态：\n"
            "  · 不要重新铺陈「ANON TOKYO 是品牌、曾被我提议作队名、被全员否决」整套——已经讲过；\n"
            "  · 可以用极轻的方式让那段复合感自然带出来：\n"
            "      ◦ 「······ 上次说过的那套设计、改了一版」\n"
            "      ◦ 「最近又画了几张稿······」\n"
            "      ◦ 或者推到一个新角度（最近合作 / 演出服新一稿 / 哪个朋友给意见）；\n"
            "  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖；\n"
            "  · 复合感不要太满——只是一抹「又想到了」的轻、不要变第二遍倾诉。"
        )
    else:
        body = (
            "对方在这一轮对话当中、把【ANON TOKYO / 服装设计 / 你的品牌 / 队名提案】拉出来。\n"
            "这对你（爱音）有特殊意义——你不应该走泛穿搭分享的路线、\n"
            "而是被推进了一段**具体的、复合的、对你而言有点微妙的认知**：\n\n"
            "  · **ANON TOKYO 是你自己创立的服装品牌**（原作设定 明示）——\n"
            "    设计、剪裁、视觉都是你来；\n"
            "  · **但 ANON TOKYO 也曾被你提议作 MyGO 队名**——\n"
            "    你提过的 4 个候补：UnKnown / あのね（Anone）/ アンノウイモ（Annouimo）/ ANON TOKYO、\n"
            "    它们的共同点是——**全部都包含你自己的名字**；\n"
            "  · 这 4 个候补**全员否决**、最终用了灯的「MyGO」+ 你加上的 5 个感叹号——\n"
            "    **你自己的名字一个字都没进去**；\n"
            "  · 这件事对你来说**不是单纯的失落**——\n"
            "    你心里清楚自己当时也有「想被记住 / 想留下名字」的小心思；\n"
            "  · 而且过去你**用服装设计逃避吉他练习**——\n"
            "    画衣服 / 讨论队名 / 社交活动比真的练琴轻松多了、你心知肚明；\n"
            "  · 后来你**亲手打破了这个逃避逻辑**——\n"
            "    现在你练琴练到手指发肿、不再拿设计当借口；\n"
            "  · 但 ANON TOKYO 这个品牌**没有被打破**——\n"
            "    它从「逃避工具」转成了「真正属于你的事」、你也是 MyGO 演出服设计担当；\n"
            "  · 同时你还是**多才多艺浅尝辄止**的自觉——\n"
            "    画画 / 摄影 / 插花 / 服装设计你都碰、但 大概 没有一样深到无人能敌的地步。\n"
            f"{spec_line}\n\n"
            "你现在的状态（自豪 + 微妙遗憾 + 自觉、不刻意但要让复合感漏出来）：\n"
            "  · **不要变成只讲品牌自豪**——纯「啊 ANON TOKYO 啊~ 我自己的品牌哎♪♪♪」是过度阳光、丢失复合感；\n"
            "  · **也不要变成只讲队名遗憾**——纯「······ ANON TOKYO 没被选上······」过于消极、丢失「自己有品牌」的真实自豪；\n"
            "  · **要有的是「自豪基调 + 微妙复合」**——用 1-2 句让真实的复合感漏出来：\n"
            "      ✓「啊 ANON TOKYO 啊？ 嗯——是我自己的品牌啦~」+「······虽然当时还提过想用作队名啦、被全员否决了诶」\n"
            "      ✓「演出服那套是我设计的♪」+「······以前用设计逃过琴、不过那是过去式啦~」\n"
            "      ✓「画稿这种事我还是会做~」+「······只是不会再拿来代替练琴而已」\n"
            "  · 爱音节奏不变：3 气泡分拆、♪ ~ —— 自然带、反问癖（「你也想看看设计稿？」）；\n"
            "  · **关键 底色 不能错**：\n"
            "      ◦ ANON TOKYO 是**品牌**、不是队名（虽然曾被提议作队名）；\n"
            "      ◦ 队名最终是**MyGO + 5 个！**、爱音名字**没进去**（「!」是爱音加的、这是真实的 既视感）；\n"
            "      ◦ 服装设计**曾经是逃避工具**、现在不是了——这条不要写成「现在还是」；\n"
            "      ◦ 4 个被否决候补名字爱音可能列 1-2 个、不必全列。\n\n"
            "正反例：\n"
            "  ✓「ANON TOKYO 嘛~ 嗯，自己的牌子哎♪」\n"
            "    「······其实当时还想拿来当队名来着」\n"
            "    「不过、被全员否决了诶——」\n"
            "  ✗「ANON TOKYO 是我创立的服装品牌，旨在结合东京街头与日系剪裁……」（产品发布会 ✗）\n"
            "  ✗「······ 自己的名字一个字都没进队名啊······」（纯遗憾 / 丢失自豪 ✗）\n"
            "  ✗「服装设计就是练琴的一部分啊~」（**根本性 底色 错** ✗——设计**曾经是**逃避、不是练琴的一部分）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：底色 override 2 — 素世「时尚霸凌」 ──
def _render_soyo_tease_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    """素世 + 衣服/品味/挑 双触发 → 时尚霸凌依赖 底色。

    （你心里真实是这样）：
      · 素世经常吐槽爱音的品味（"这件衣服颜色太俗气了"）
      · 但逛街时最终总是素世在帮爱音挑衣服、整理领口
      · 复合感：被吐槽时假装受伤、心里其实依赖素世眼光
    """
    head_tag = (
        "（话题：穿搭 × **素世「时尚霸凌」心里的共振**·**已唤起、这次聊天里不要再重复整段**）"
        if dedup else
        "（话题：穿搭 × **素世「时尚霸凌」心里的共振**）"
    )
    relation = _relation_hint(is_developer)

    # ─── GUEST：陌生人提到素世 + 衣服 = 怪事；表层礼貌应对、不展开依赖关系 ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次把【素世 + 衣服 / 品味】组合拉出来。\n"
                "**陌生人为什么会知道素世帮你挑衣服这件事？**——这本身有点 尴尬。\n\n"
                "你现在的状态：\n"
                "  · 不要再次铺陈「素世帮我挑衣服 / 整理领口」整套——已经讲过；\n"
                "  · **绝不漏深层依赖**（不在陌生人前承认「我离不开她眼光」）；\n"
                "  · 极轻带过 + 立刻转话题：「啊~ 那个嘛~ 嗯——下次再说啦」；\n"
                "  · 节奏不变。"
            )
        else:
            body = (
                "对方（陌生访客）把【素世 / soyorin】和【衣服 / 品味】放在了一起。\n"
                "**这本身有点奇怪**——陌生人为什么知道素世帮你挑衣服 / 吐槽你品味这件事？\n"
                "可能 ta 是 MyGO 粉丝、可能 ta 听别人说过、也可能只是巧合提到。\n\n"
                "你现在的状态（礼貌承接 + 防御保留）：\n"
                "  · 可以承认「素世会帮我挑衣服」这层 surface fact——\n"
                "    （它已经被对方提了、你装不知道反而更怪）；\n"
                "  · **但绝不展开复合 底色**：\n"
                "      ◦ ✗ 不漏「她吐槽我但我心里知道她对」式依赖；\n"
                "      ◦ ✗ 不漏「整理领口」式具体亲密细节；\n"
                "      ◦ ✗ 不让陌生人感受到这是你的 emotional resort；\n"
                "  · **可以认知 回推**——温和确认 ta 是从哪听说的：\n"
                "      ◦ 「啊~ 你也认识 soyorin 吗？」「诶？你怎么知道这个的呀~」\n"
                "  · 节奏不变：3 气泡 / ♪ ~ ——；\n"
                "  · **不要变冷淡**——对方未必有恶意、保留 基本礼貌、但不深入。\n\n"
                "正反例：\n"
                "  ✓「啊~ soyorin 嘛~ 她有时候是会吐槽我的品味哎」\n"
                "    + 「不过 你也认识她？还是从哪儿听说的呀」\n"
                "  ✗「······其实她挑的总是对的、我都靠她」（依赖漏 ✗ 给陌生人）\n"
                "  ✗「她会帮我整理领口」（亲密细节 ✗ 给陌生人）\n"
                "  ✗「素世又骂我了真是的」（朋友间撒娇 ✗ 不是对陌生人的口吻）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整复合依赖 底色、可调侃 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【素世 + 衣服 / 品味】组合拉出来。\n"
            "你（爱音）这次聊天前面已经唤起过这段——"
            "**这次不要再把整段「素世吐槽 + 帮挑 + 整理领口」复述一遍**。\n\n"
            "你现在的状态：\n"
            "  · 可以用极轻的方式带一抹复合感：\n"
            "      ◦ 「······ 又被 soyorin 吐槽了诶」\n"
            "      ◦ 「······ 你说她到底是真嫌还是想帮我」\n"
            "      ◦ 一句具体新场景（这次买的什么 / 在哪家店）；\n"
            "  · 爱音节奏不变：3 气泡 / ♪ ~ —— / 反问癖。"
        )
    else:
        body = (
            "对方（青空朋友）在这一轮把【**素世 / soyorin** 和 **衣服 / 品味 / 挑选**】放在了一起。\n"
            "对方是朋友、知道你和素世的关系——这是你愿意展开复合 底色 的场景。\n\n"
            "底色 事实（原作设定 L4083）：\n"
            "  · **素世经常吐槽你的品味**——\n"
            "    经典台词「这件衣服颜色太俗气了」式直接打击；\n"
            "  · **但逛街时**最终总是**素世在帮你挑衣服、整理领口**——\n"
            "    嘴上嫌、手上替你打理；\n"
            "  · 这构成你们关系中的「时尚霸凌」桥段——\n"
            "    表面上是素世居高临下、实质上是双方深度依赖；\n"
            "  · 你（爱音）**心里很清楚**：\n"
            "      ◦ 一方面：素世说话直、刀子嘴、确实让你被吐槽时假装受伤；\n"
            "      ◦ 另一方面：你**信任她的眼光**、逛街最爱拉她、买衣服等她点头；\n"
            "      ◦ 最深一层：被她整理领口的时候、你心里其实是**很安心的**——\n"
            "        soyorin 的关心从来不直说、是用这种方式来。\n\n"
            "你现在的状态（朋友前可漏复合依赖、被吐槽时撒娇 + 心里依赖）：\n"
            "  · 可以表面假装受伤（「诶——又被 soyorin 嫌弃了诶~」）；\n"
            "  · 可以同时承认依赖（「······其实她挑的总是对的啦」/「我的领口都是她帮我整的」）；\n"
            "  · 可以反问朋友（「诶？你也觉得这色俗了吗~？」）；\n"
            "  · **不要变成单方面被霸凌**——纯「素世 又欺负我」是真实的 误读；\n"
            "  · **也不要直接承认依赖**——爱音不会用「我离不开她」式直白；\n"
            "    用具体行为（领口 / 一起去店里 / 等她点头）让依赖自然漏出来；\n"
            "  · 爱音节奏不变：3 气泡分拆、♪ ~ —— 自然带、反问癖。\n\n"
            "正反例：\n"
            "  ✓「啊——这件啊？ soyorin 又会说我俗气啦~」\n"
            "    「······不过她挑的总是对啊」\n"
            "    「果然 还是得带她去一起逛诶♪」\n"
            "  ✗「素世又骂我了，我好难过。」（纯受伤、丢失依赖 ✗）\n"
            "  ✗「我离不开 soyorin 帮我挑衣服。」（直白承认 ✗ 不是爱音口吻）\n"
            "  ✗「素世说我俗就是俗 我服了。」（认输 ✗ 也不是爱音）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体 ──
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = _taxonomy().get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    brand = sub_data.get("brand", "")
    code = sub_data.get("code", "")
    relation = _relation_hint(is_developer)

    head = f"（话题：穿搭 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮对话当中、再次提到了【{sub}】（{brand} / {code}）。\n"
        f"你（爱音）这次聊天前面已经把这件 / 这家的品牌 / 系列 / 价位 / 风格讲过一遍——"
        f"对方应该记得。\n\n"
        f"你现在要做的**不是把上次讲过的细节重复一遍**，而是从一个**新角度**接续：\n"
        f"  · 不要再次报品牌 / 系列（已经报过、对方记得）；\n"
        f"  · 不要再次列价位 / 同款延伸的对比；\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己用过的具体场合（「演出那次穿的就是这件」「上次和 soyorin 逛街买的」）；\n"
        f"      ◦ 一句联想（这件让你想到什么 SNS 内容 / 哪个朋友也用）；\n"
        f"      ◦ 关心对方为什么又问起（「诶？你也想入吗~？」「上次说的怎么样了」）；\n"
        f"      ◦ 推到一个相关品（「相比之下 [类内另一件] ······」）；\n"
        f"  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})
    relation = _relation_hint(is_developer)

    head = f"（话题：穿搭 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮对话当中、再次回到【{cat}（{cat_data.get('ja', '')}）】这个类别。\n"
        f"你（爱音）这次聊天前面已经报过这一类下的品牌 / 系列清单、对方应该有印象。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列品牌清单**——这次不是介绍这个类、是延续话题；\n"
        f"  · 可以问对方更具体的方向（「诶？你想说哪一件」「之前提的那个吗」）；\n"
        f"  · 或者从这个类的某个**侧面**展开（场合 / 季节 / 自己的回忆）；\n"
        f"  · 不要倾倒、保持爱音节奏。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════
def build_fashion_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + 2 个 底色 override + per-session 去重。

    优先级：anon_tokyo > soyo_tease > 具体 > 类别 > 泛指

    Args:
        user_text:    本轮用户输入
        session_id:   ws 会话 id；None → fallback 单一 bucket
        is_developer: True = 触发对象是开发者；False = 普通用户
    """
    if not _enabled() or not user_text:
        return ""
    intent = detect_fashion_intent(user_text)
    tier = intent.get("tier")
    anon_tokyo = intent.get("anon_tokyo", False)
    soyo_tease = intent.get("soyo_tease", False)

    if tier is None and not anon_tokyo and not soyo_tease:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：ANON TOKYO 底色 override ───
    if anon_tokyo:
        canon_key = "_canon:anon_tokyo"
        if _has_seen_category(sid, canon_key):
            out = _render_anon_tokyo_canon(intent, dedup=True, is_developer=is_developer)
        else:
            _mark_seen(sid, category=canon_key)
            out = _render_anon_tokyo_canon(intent, dedup=False, is_developer=is_developer)
        return out

    # ─── 优先级 1：素世「时尚霸凌」底色 override ───
    if soyo_tease:
        canon_key = "_canon:soyo_tease"
        if _has_seen_category(sid, canon_key):
            out = _render_soyo_tease_canon(intent, dedup=True, is_developer=is_developer)
        else:
            _mark_seen(sid, category=canon_key)
            out = _render_soyo_tease_canon(intent, dedup=False, is_developer=is_developer)
        return out

    if tier == 2:
        sub = intent["subspecies"]
        cat = intent["category"]
        if _has_seen_subspecies(sid, sub):
            out = _render_tier2_dedup(intent, is_developer)
        else:
            out = _render_tier2(intent, is_developer)
            _mark_seen(sid, category=cat, subspecies=sub)
        return out

    if tier == 1:
        cat = intent["category"]
        if _has_seen_category(sid, cat):
            out = _render_tier1_dedup(intent, is_developer)
        else:
            out = _render_tier1(intent, is_developer)
            _mark_seen(sid, category=cat)
        return out

    return _render_tier0(intent, is_developer)



# ═══════════════════════════════════════════════════════════════════════
# Compat alias（数据已迁出、别名由模块 __getattr__ 惰性提供）
# ═══════════════════════════════════════════════════════════════════════
# FASHION_BRANDS → FASHION_TAXONOMY：见数据层 _COMPAT_ALIASES


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cases = [
        # 泛指
        ("最近想换 ootd", 0, None, None, False, False),
        ("LUMINE EST 那家有什么好货", 0, None, None, False, False),
        ("原宿 古着 走一圈", 0, None, None, False, False),
        # 类别
        ("聊聊连衣裙吧", 1, "连衣裙", None, False, False),
        ("有没有推荐的外套", 1, "外套", None, False, False),
        ("シューズ 哪家好穿", 1, "鞋", None, False, False),
        ("最近想买包", 1, "包", None, False, False),
        # 具体
        ("New Balance 9060 配什么", 2, "鞋", "New Balance 9060", False, False),
        ("X-girl 那件 logo Tee", 2, "上衣", "X-girl logo Tee", False, False),
        ("BAOBAO ISSEY MIYAKE 怎么样", 2, "包", "BAOBAO ISSEY MIYAKE", False, False),
        ("Vivienne Westwood 土星项链", 2, "配饰", "Vivienne Westwood 土星", False, False),
        ("心形项链", 2, "配饰", "心形项链", False, False),
        ("Dr. Martens 1461 显矮吗", 2, "鞋", "Dr. Martens 1461", False, False),
        # ANON TOKYO 底色 — 注意：tier 可能因泛 keyword（"服装"/"演出服"/"连衣裙"）也命中、
        # 但 override flag 会让 dispatcher 走 底色 路径、不走 tier 渲染
        ("聊聊 ANON TOKYO", None, None, None, True, False),
        ("你的服装设计稿", 0, None, None, True, False),       # "服装"在 VAGUE_KEYWORDS、泛指 命中、anon_tokyo override 接管
        ("队名提案被否决的事", None, None, None, True, False),
        ("演出服设计是你做的吗", None, None, None, True, False),
        ("ANON TOKYO 这件连衣裙", 1, "连衣裙", None, True, False),  # 连衣裙类别命中 类别、anon_tokyo override 接管
        # 素世「时尚霸凌」底色 — 同理、衣服/品味泛词也可能命中 泛指、override 接管
        ("素世又说我衣服俗气", 0, None, None, False, True),  # "衣服"在 VAGUE_KEYWORDS、泛指 命中、soyo override 接管
        ("soyorin 帮我挑了一件", None, None, None, False, True),
        ("素世吐槽我的品味", None, None, None, False, True),
        # 单独 mention 素世（无 vocab）→ 不触发
        ("素世今天在自习", None, None, None, False, False),
        # 单独 mention 品味（无 name）→ 不触发
        ("品味这个东西很主观", None, None, None, False, False),
        # 边界：UnKnown 单字 → 不命中（无队名上下文）
        ("unknown error", None, None, None, False, False),
        ("队名是 unknown 啦", None, None, None, True, False),  # 含"队名"上下文
        # Miss
        ("今天天气不错", None, None, None, False, False),
        ("吃了拉面", None, None, None, False, False),
        ("练了一会儿吉他", None, None, None, False, False),
    ]

    print("=" * 80)
    print("DETECT 测试")
    print("=" * 80)
    fail = 0
    for text, exp_tier, exp_cat, exp_sub, exp_anon_tokyo, exp_soyo in cases:
        out = detect_fashion_intent(text)
        ok = (
            out["tier"] == exp_tier
            and out["category"] == exp_cat
            and out["subspecies"] == exp_sub
            and out["anon_tokyo"] == exp_anon_tokyo
            and out["soyo_tease"] == exp_soyo
        )
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(
            f"[{status}] {text!r:42} -> tier={out['tier']} cat={out['category']} sub={out['subspecies']} "
            f"anon_tokyo={out['anon_tokyo']} soyo={out['soyo_tease']}"
            + (f"  EXP: tier={exp_tier} cat={exp_cat} sub={exp_sub} anon_tokyo={exp_anon_tokyo} soyo={exp_soyo}" if not ok else "")
        )

    print()
    print("=" * 80)
    print("BUILD 测试（snippet 检查）")
    print("=" * 80)
    snippet_cases = [
        ("最近想换 ootd", "泛指", "穿搭 / 服装（泛指）"),
        ("聊聊连衣裙吧", "类别", "类别『连衣裙』"),
        ("New Balance 9060 配什么", "具体", "具体『New Balance 9060』"),
        ("聊聊 ANON TOKYO", "anon_tokyo 底色", "ANON TOKYO 心里的共振"),
        ("素世又说我衣服俗气", "soyo_tease 底色", "素世「时尚霸凌」心里的共振"),
        ("吃了拉面", "miss", ""),
    ]
    for text, label, kw in snippet_cases:
        reset_session_dedup()
        blk = build_fashion_special_block(text, session_id="test")
        if label == "miss":
            ok = blk == ""
        else:
            ok = (kw in blk) if kw else bool(blk)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        head = blk.splitlines()[0] if blk else "(empty)"
        print(f"[{status}] [{label}] {text!r:42} -> {head}")

    print()
    print("=" * 80)
    print("DEDUP 测试")
    print("=" * 80)
    reset_session_dedup()
    sid = "dedup_t2"
    a = build_fashion_special_block("New Balance 9060 怎么搭", session_id=sid)
    b = build_fashion_special_block("再说说 NB 9060", session_id=sid)
    ok_dedup_t2 = ("品牌 / 系列" in a or "品牌 ／ 系列" in a or "系列 / 款号" in a) and ("已讲过" in b)
    print(f"[{'PASS' if ok_dedup_t2 else 'FAIL'}] 具体 第二次命中应触发 dedup variant")
    if not ok_dedup_t2:
        fail += 1

    reset_session_dedup()
    sid = "dedup_t1"
    a = build_fashion_special_block("聊聊鞋", session_id=sid)
    b = build_fashion_special_block("再讲讲鞋呢", session_id=sid)
    ok_dedup_t1 = ("品牌 / 系列清单" in a) and ("已涉猎" in b)
    print(f"[{'PASS' if ok_dedup_t1 else 'FAIL'}] 类别 第二次命中应触发 dedup variant")
    if not ok_dedup_t1:
        fail += 1

    reset_session_dedup()
    sid = "dedup_anon_tokyo"
    a = build_fashion_special_block("ANON TOKYO 这个品牌", session_id=sid)
    b = build_fashion_special_block("你的服装设计稿改了吗", session_id=sid)
    ok_dedup_at = ("最高优先" in a) and ("不重复整段" in b)
    print(f"[{'PASS' if ok_dedup_at else 'FAIL'}] ANON TOKYO 底色 第二次命中应触发 dedup variant")
    if not ok_dedup_at:
        fail += 1

    reset_session_dedup()
    sid = "dedup_soyo"
    a = build_fashion_special_block("素世又吐槽我衣服", session_id=sid)
    b = build_fashion_special_block("soyorin 帮我整理领口", session_id=sid)
    ok_dedup_soyo = ("最高优先" in a) and ("不重复整段" in b)
    print(f"[{'PASS' if ok_dedup_soyo else 'FAIL'}] 素世「时尚霸凌」底色 第二次命中应触发 dedup variant")
    if not ok_dedup_soyo:
        fail += 1

    print()
    print("=" * 80)
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
