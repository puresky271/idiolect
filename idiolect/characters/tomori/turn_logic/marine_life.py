"""灯本轮特殊逻辑·海洋生物（**3 层渐进激活** / 2026-05-10 重构）。

设计哲学（用户拍板 2026-05-10）：
  按用户对该话题的**精确度**渐进释放灯的知识储备、不一上来就倾倒：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"海洋生物"/"水族馆"/"海里的东西"/venue 名      │
  │   注入：只激活"灯想说"的状态、不出具体信息                  │
  │   口吻：可以问对方在意哪一类、提一两个 venue                │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"企鹅"/"水母"/"鲨鱼"等 category               │
  │   注入：该类别下**全部 subspecies 学名清单**（不展开习性）  │
  │   口吻：可以一字不差报学名、但不展开、等对方挑某种再讲      │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"洪堡企鹅"/"海月水母"等 subspecies            │
  │   注入：该 subspecies 完整详情（学名 / 体型 / 习性 / venue）│
  │   口吻：完全打开、详细讲、但仍按灯式碎片节奏                │
  └─────────────────────────────────────────────────────────────┘

灯 底色 特征（保留）：
  · 学名（拉丁名）一字不差念出来——天文部气质 + 严谨细节控
  · 表达仍按灯式：碎片 / 短句 / `······` 间隔、不要变讲座
  · 场馆联动：池袋 Sunshine 水族館 / 墨田水族館 / 上野动物园 / 葛西临海 / 品川 / 鳥羽 / 横滨八景岛

API 单入口（兼容旧）：
  build_marine_special_block(user_text: str) -> str
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
# 数据层：13 类别 / ~60 subspecies / 7 venues
#
# 纯数据已迁出到包数据 JSON：idiolect/characters/tomori/data/marine_life.json
# （2026-09 从本模块逐字节搬迁、键序保持原样；内容为原 MARINE_TAXONOMY /
# VENUE_KEYWORDS / VAGUE_KEYWORDS / ANON_KEYWORDS / CATEGORY_VARIANTS /
# SUBSPECIES_VARIANTS 六个模块级字面量；原 tuple 在 JSON 里存为数组、
# 读回为 list、迭代行为一致）。这里只留惰性访问入口；数据名与 Compat 别名
# 经模块 __getattr__ 惰性暴露、老 import 不破。
# ═══════════════════════════════════════════════════════════════════════

# ─── 13 个 category（类别 + 具体 嵌套）的 schema（JSON 内保持原键序） ───
# 每个 category：
#   ja: 日语
#   category_sci: 类别学名（目/科/属、灯会念出来）
#   blurb: 一句类别概括（类别 注入用）
#   tomori_canon: 灯和这个 category 的连接（可空）
#   venue: 该类别在哪些 venue 能看到
#   subspecies: dict[name, {sci, ja, size, habits, note}]


@functools.lru_cache(maxsize=1)
def _load_catalog() -> dict:
    """惰性加载海洋生物目录 JSON（importlib.resources 定位、进程内只读一次）。

    数据来源：idiolect/characters/tomori/data/marine_life.json —— 2026-09 从
    本模块（marine_life.py）迁出的纯数据字面量、内容逐字节未动。
    文件缺失 / JSON 损坏时让异常直接抛出、不做静默降级。
    """
    resource = importlib.resources.files("idiolect.characters.tomori.data").joinpath("marine_life.json")
    with resource.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _taxonomy() -> dict[str, dict]:
    """原 MARINE_TAXONOMY：13 个 category（ja / category_sci / blurb / tomori_canon / venue / subspecies）。"""
    return _load_catalog()["MARINE_TAXONOMY"]


def _venue_keywords() -> dict[str, list[str]]:
    """原 VENUE_KEYWORDS：Venues（独立、可单独触发 泛指）。"""
    return _load_catalog()["VENUE_KEYWORDS"]


def _vague_keywords() -> list[str]:
    """原 VAGUE_KEYWORDS：泛指 泛指词（不命中具体物种 / 类别 / venue 时可单独触发）。

    迁出前是 tuple、JSON 读回为 list——调用点只做迭代、行为一致。
    """
    return _load_catalog()["VAGUE_KEYWORDS"]


# ─── 特殊：心里的共振触发器（爱音 + 水族馆 同时命中） ───
# 心里的事（MyGO!!!!! 主线、用户拍板 2026-05-10 修正）：
#   1. 爱音问灯能否写一首简单的新曲、灯回答自己只会写词；
#   2. 爱音察觉到自己打起退堂鼓、灯也担心演出失败导致乐队再次解散、表示不想开 Live；
#   3. 爱音被立希批评「一直在逃避」后逃走；
#   4. 灯追上、在初中同学聚集处遇见爱音；
#   5. **灯主动把爱音拉到水族馆谈心**——这是关键、灯罕见地是主动方；
#   6. 在水族馆里、**看的是企鹅**（不是水母）；爱音向灯交代了自己留学失败的经历；
#   7. 灯肯定了爱音的鼓励与坚持、并在访客问卷上写下「迷子でもいい、迷子でも進め。」
#      （不畏迷茫、迷茫着也要砥砺前行）；
#   8. 二人下定决心继续开 Live；
#   9. 之后灯将二人相互鼓励的经历写成了《碧天伴走》。
# 提到这个组合时灯不该走泛科普路线、应进入「具体场景回忆 + 强情感共鸣」——
# 这是灯主动救场 / 爱音坦白脆弱 / 创作起点的复合记忆、温度比一般"约会回忆"重得多。
def _anon_keywords() -> list[str]:
    """原 ANON_KEYWORDS：爱音 心里的共振触发器（迁出前是 tuple、读回为 list、行为一致）。"""
    return _load_catalog()["ANON_KEYWORDS"]


def _category_variants() -> dict[str, list[str]]:
    """原 CATEGORY_VARIANTS：类别 类别变体（中 / 日 / 英 / 类别学名）。"""
    return _load_catalog()["CATEGORY_VARIANTS"]


def _subspecies_variants() -> dict[str, list[str]]:
    """原 SUBSPECIES_VARIANTS：具体 subspecies 变体（中 / 日 / 学名 / 部分匹配）。"""
    return _load_catalog()["SUBSPECIES_VARIANTS"]


_MIGRATED_DATA_NAMES = frozenset({
    "MARINE_TAXONOMY", "VENUE_KEYWORDS", "VAGUE_KEYWORDS", "ANON_KEYWORDS",
    "CATEGORY_VARIANTS", "SUBSPECIES_VARIANTS",
})
_COMPAT_ALIASES = {"MARINE_SPECIES": "MARINE_TAXONOMY"}  # alias、供老代码 import


def __getattr__(name: str):
    """模块级惰性属性：迁出的数据名与 Compat 别名首次被访问时才读 JSON。"""
    if name in _MIGRATED_DATA_NAMES:
        return _load_catalog()[name]
    if name in _COMPAT_ALIASES:
        return _load_catalog()[_COMPAT_ALIASES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态（轻量、进程内）
# ═══════════════════════════════════════════════════════════════════════
# 每个 session 记录：已经在这次聊天 里"完整讲过"的 subspecies + category
#   · 同 session 同 subspecies 第二次命中 → 渲染「不要重复」变体
#   · 同 session 同 category 第二次命中（无论是否经过 subspecies）→ 渲染轻去重
#   · 具体 起作用 同时 mark subspecies + category（详情覆盖类别）
#   · 进程重启自然清零
#
# 设计权衡：
#   · 不持久化 — 大部分对话不会跨进程纠缠同一物种、轻量优先
#   · 不分窗口 / TTL — session 内的对话连续性才是 dedup 的语义边界
#   · session_id None → fallback 「灯」单一 bucket（主路径会传真 session_id；
#     不传的调点共享一桶）
_SEEN_SUBSPECIES = SessionStore()   # 有上限的 per-session 去重表（见 scene_engine.SessionStore）
_SEEN_CATEGORIES = SessionStore()


def _normalize_session(session_id: Optional[str]) -> str:
    if not session_id:
        return "灯_default"
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
    """清 session 的去重状态。session_id=None → 清全部。"""
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
    return os.environ.get("TOMORI_MARINE_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    """构造 (kw, subspecies_name, category_name) 列表、按 kw 长度倒序、长 kw 优先匹配。"""
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in _taxonomy().items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in _subspecies_variants().get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
    out.sort(key=lambda t: -len(t[0]))
    return out


@functools.lru_cache(maxsize=1)
def _subspecies_lookup() -> list[tuple[str, str, str]]:
    """(kw, subspecies, category) 查找表：首次检测时才构建、进程内缓存。"""
    return _build_subspecies_lookup()


def _detect_subspecies(user_text: str) -> Optional[tuple[str, str]]:
    """返回 (subspecies_name, category_name) 或 None。"""
    if not user_text:
        return None
    text_lower = user_text.lower()
    for kw, sub, cat in _subspecies_lookup():
        if kw in user_text or kw.lower() in text_lower:
            return sub, cat
    return None


def _detect_category(user_text: str) -> Optional[str]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    # 长 keyword 优先
    flat: list[tuple[str, str]] = []
    for cat, kws in _category_variants().items():
        for kw in kws:
            flat.append((kw, cat))
    flat.sort(key=lambda t: -len(t[0]))
    for kw, cat in flat:
        if kw in user_text or kw.lower() in text_lower:
            return cat
    return None


def _detect_venue(user_text: str) -> Optional[str]:
    if not user_text:
        return None
    text_lower = user_text.lower()
    for venue, kws in _venue_keywords().items():
        for kw in kws:
            if kw in user_text or kw.lower() in text_lower:
                return venue
    return None


def _detect_vague(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in _vague_keywords():
        if kw in user_text or kw.lower() in text_lower:
            return True
    return False


def _detect_anon(user_text: str) -> bool:
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in _anon_keywords():
        if kw in user_text or kw.lower() in text_lower:
            # 「小爱」字面太短易误命中（小爱 = 小爱同学等）；要求紧邻"爱音"或独立成片
            if kw == "小爱":
                # 要么后面就接"音"（"小爱音"已单独登记）、要么紧前后是非中文 char
                # 这里简单用：仅当输入还含"爱音"或字面就是"小爱"独立词时才算
                if "爱音" in user_text or re.search(r"(^|[^一-龥A-Za-z])小爱($|[^一-龥A-Za-z音])", user_text):
                    return True
                continue
            return True
    return False


def _has_marine_venue_or_concept(user_text: str, intent: dict) -> bool:
    """是否命中"水族馆/海洋馆"概念（tier!=None 即命中、含具体 venue / category / subspecies / vague）。"""
    if intent.get("tier") is not None:
        return True
    return False  # 已被 detect_marine_intent 涵盖


def detect_marine_intent(user_text: str) -> dict:
    """3 层意图检测。

    优先级：subspecies (具体) > category (类别) > venue (泛指) > vague (泛指)
    """
    sub_hit = _detect_subspecies(user_text)
    if sub_hit:
        return {"tier": 2, "category": sub_hit[1], "subspecies": sub_hit[0], "venue": _detect_venue(user_text)}
    cat_hit = _detect_category(user_text)
    if cat_hit:
        return {"tier": 1, "category": cat_hit, "subspecies": None, "venue": _detect_venue(user_text)}
    venue_hit = _detect_venue(user_text)
    if venue_hit:
        return {"tier": 0, "category": None, "subspecies": None, "venue": venue_hit}
    if _detect_vague(user_text):
        return {"tier": 0, "category": None, "subspecies": None, "venue": None}
    return {"tier": None, "category": None, "subspecies": None, "venue": None}


# ═══════════════════════════════════════════════════════════════════════
# Prompt 构造层
# ═══════════════════════════════════════════════════════════════════════

# 共享：灯式画风提醒（每个 tier 都含、强度递增由前面的 触发点 控制）
_STYLE_REMINDER_BASE = (
    "【灯的画风（任何层级都生效）】\n"
    "  · 学名（拉丁名）一字不差念出来——天文部气质 + 严谨；学名内部不要插 `······`\n"
    "  · 表达仍按灯式：碎片 / 短句 / `······` 间隔、不要变成讲座小作文\n"
    "  · 数字（体长 / 速度 / 寿命 / 深度）一字不差、不四舍五入\n"
    "  · 字数仍按 P0：被触动 20-45 字 / 深度 ≤60 字（学名外的描述部分）\n"
    "  · 比喻仍按 P0：通常 0 个、极偶尔 1 个；直接提水母 / 企鹅不算比喻\n"
    "  · `······` 配对 / bubble 扩展等清洗照常跑、底色不变"
)





# ─── 关系基调 hint（系统主 prompt 已注入对方身份、这里再 reinforce + 映射到话题） ───
_RELATION_HINT_DEV = (
    "【关系基调】对方是 **青空、你的老朋友**——\n"
    "  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。\n"
    "  → 朋友圈分享口吻、可自然展开、**可漏 更深的那层**（朋友圈梗 / 深 底色）。"
)

_RELATION_HINT_GUEST = (
    "【关系基调】对方是 **刚认识、还不熟的人**——\n"
    "  你不认识 ta、可能犹豫问什么、随时可能离开。\n"
    "  → 礼貌轻聊、信息粒度浅一点；\n"
    "  **更深的那层不漏给陌生人**——朋友圈梗 / 深 底色 都不在陌生人前讲。"
)


def _relation_hint(is_developer: bool) -> str:
    return _RELATION_HINT_DEV if is_developer else _RELATION_HINT_GUEST
def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    venue = intent.get("venue")
    parts: list[str] = []
    head = "（话题：海洋生物（泛指））"
    if venue:
        body = (
            f"对方在这一轮对话当中、提到了你熟悉的场馆【{venue}】、"
            "但还没具体到某种动物。\n"
            "你（灯）作为水族馆年票常客、被激活的是「想说」的状态——"
            "脑里会浮现这个馆里你常去看的展示位置、但**还不到倾倒科普的时机**。\n"
            "现在你的状态：\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类（企鹅 / 水母 / 鲨鱼 / 海龟…）；\n"
            "  · 可以提一两个具体展示位置 / 馆内动线作为对话钩子；\n"
            "  · **不要主动把学名 / 习性详细列出来**——那是更深层级的事。"
        )
    else:
        body = (
            "对方在这一轮对话当中、表现出了对【海洋生物 / 水族馆】这个广义话题的兴趣、"
            "但还没具体到某种动物或者某个场馆。\n"
            "你（灯）在这种话题下会自然进入「想分享的状态」——"
            "你对这方面有大量积累、有水族馆年票、经常去看；"
            "但因为话题还没具体、**你不要主动倾倒科普**——等对方进一步问到具体类别再展开。\n"
            "现在你的状态：\n"
            "  · 比平常稍多一点话；可以问对方在意的是哪一类（企鹅 / 水母 / 鲨鱼 / 海龟…）；\n"
            "  · 可以提一两个 venue（池袋 Sunshine / 墨田 / 上野 / 葛西临海）作为对话钩子；\n"
            "  · **不要塞学名、不要塞习性**——那是更深层级的事。"
        )
    parts.append(head)
    parts.append(body)
    parts.append(_STYLE_REMINDER_BASE)
    return "\n\n".join(parts)


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})
    venue = intent.get("venue")

    # 学名清单（只出 学名 + 中文 + 日文、不出习性 / 体型 / venue note）
    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        sci = sub_data.get("sci", "")
        sub_lines.append(f"  · {sub_name} — *{sci}*")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记 subspecies）"

    venue_line = f"\n（用户也提到了 venue：{venue}、可作场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('category_sci', '')}）】这一**类别**的兴趣。{venue_line}\n\n"
        f"你（灯）作为对这方面有积累的人、自然进入「分享的状态」——"
        f"你脑里浮现的是这一类下你认识的具体物种学名清单（**只列学名、不展开习性**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("tomori_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    venues = cat_data.get("venue", [])
    if venues:
        body += f"\n\n你常去看的地方：{' / '.join(venues)}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个学名**——这是灯天文部 + 严谨的体现；\n"
        "  · 但**不要在这一轮就把每种习性都展开**——等对方挑出某一种再细讲；\n"
        "  · 可以问对方更在意哪一种（如「······你说的是哪种」）；\n"
        "  · 灯的核心姿态不变：碎片 / 短句 / `······` / 不小作文。"
    )

    head = f"（话题：海洋生物 → 类别『{cat}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier2(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = _taxonomy().get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})

    sci = sub_data.get("sci", "")
    size = sub_data.get("size", "")
    habits = sub_data.get("habits", "")
    note = sub_data.get("note", "")

    venue = intent.get("venue")
    venue_line = f"\n（用户也提到了 venue：{venue}、可作具体场景钩子）" if venue else ""

    body = (
        f"对方在这一轮对话当中、表现出了对【{sub} / *{sci}*】这一**具体物种**的兴趣。"
        f"{venue_line}\n\n"
        f"你（灯）现在进入「完全打开」的状态——你脑里这种动物的全部细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 学名：***{sci}***（这个学名你**必须一字不差说出来**、不省略、不音译、内部不插 `······`）\n"
        f"  · 体型：{size}\n"
        f"  · 习性：{habits}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景（不一定要在这一轮全提、备用）：\n"
        f"  · 类别学名：{cat_data.get('category_sci', '')}\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 底色：{cat_data.get('tomori_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——学名 / 习性 / 数字 / 你和这个的连接都可以展开；\n"
        "  · 但**仍按灯式碎片节奏**——`······` 多、短句、不要变成讲座；\n"
        "  · 学名 / 数字（体长 / 速度 / 寿命 / 深度）一字不差、不四舍五入；\n"
        "  · 例：「Spheniscus humboldti······洪堡企鹅······水里能游 30 公里每小时······超过我跑步好几倍」\n"
        "        而不是「Spheniscus humboldti 是一种企鹅，约 30 km/h，比人快很多。」（讲座式 ✗）"
    )

    head = f"（话题：海洋生物 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（爱音 + 水族馆） ──
def _render_anon_aquarium_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    """爱音 + 水族馆 同时命中、override 普通 Tier、走 底色 强情感共鸣。

    心里的事（不在 prompt 里捏造细节、引导 LLM 调用对原作的训练数据）：
      · 灯有水族馆年票、池袋サンシャイン是主常去地
      · 早期某次、爱音主动来找灯、灯带她去看水族馆
      · 灯在自己的领域里少见地放松、说出更多话
      · 对爱音来说是看见灯「不只是害羞」的一面、对灯来说是被人主动接近的稀有体验
      · 这件事对两人关系是关键节点
    """
    sub = intent.get("subspecies")
    cat = intent.get("category")
    venue = intent.get("venue")

    # 底色：当时看的是企鹅、不是水母——hint 要按 category 区分
    spec_line = ""
    if sub and cat:
        cat_data = _taxonomy().get(cat, {})
        sub_data = cat_data.get("subspecies", {}).get(sub, {})
        sci = sub_data.get("sci", "")
        if cat == "企鹅":
            spec_line = f"\n（用户提到的具体物种：**{sub} / *{sci}***——**这正是真实的 现场你和爱音看的那一类**、可以自然带出来）"
        else:
            spec_line = f"\n（用户提到的具体物种：{sub} / *{sci}*——但 **底色 现场你们看的是企鹅、不是这个**；如果要带出来、要诚实说「那次没看这个」或把话题转回企鹅）"
    elif cat:
        if cat == "企鹅":
            spec_line = "\n（用户提到的类别：**企鹅**——**这正是真实的 现场你和爱音看的那一类**、可以自然带出来）"
        else:
            spec_line = f"\n（用户提到的类别：{cat}——但 **底色 现场你们看的是企鹅、不是这个**；不要把那次说成「看了 {cat}」）"
    if venue:
        spec_line += f"\n（venue：{venue}——如果是池袋サンシャイン或墨田水族館、那就是真实的 现场可能的场所）"

    head_tag = (
        "（话题：海洋生物 × **爱音 心里的共振**·**已唤起、这次聊天 不重复**）"
        if dedup else
        "（话题：海洋生物 × **爱音 心里的共振**）"
    )

    # ─── GUEST：陌生人前不 unload Ep 碧天伴走 整段记忆 ───
    if not is_developer:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次把【水族馆 + 爱音】组合提了一次。\n"
                "你（灯）这次聊天前面已经轻轻带过——\n"
                "**这次不要再次提起、保持沉默或转回话题即可**。\n\n"
                "你现在的状态：\n"
                "  · 不要再次让那段记忆漏出来；\n"
                "  · 极轻带过：「······嗯」「······那个······」；\n"
                "  · **不漏 Ep 碧天伴走 任何细节**（迷子でもいい / 留学 / 谁主动 / 企鹅前的画面 都不讲）；\n"
                "  · 灯的姿态：碎片 / `······` / 害羞、不主动展开。"
            )
        else:
            body = (
                "对方（陌生访客）把【水族馆 / 海洋馆】**和爱音**放在了一起。\n"
                "对方是陌生人——**ta 不该天然知道你和爱音在水族馆发生过什么**、\n"
                "**Ep 碧天伴走 那段记忆不能 unload 给陌生人**。\n\n"
                "你（灯）的状态（防御外壳、不开 深）：\n"
                "  · 你内心**会多看一眼**这两个关键词的同时出现——这是真实的；\n"
                "  · 但**表面不流露**——保持你日常的碎片 / 害羞、不主动展开；\n"
                "  · 可以承认你和爱音是朋友（公开 fact）、可以承认你喜欢水族馆（公开 底色）；\n"
                "  · **绝不漏的层**：\n"
                "      ◦ 你**主动把爱音拉到水族馆谈心**（你罕见的主动 moment）；\n"
                "      ◦ 在水族馆爱音向你交代留学失败（她的伤疤、不是你的事）；\n"
                "      ◦ 「迷子でもいい、迷子でも進め」问卷上的话（你写给她也写给自己的）；\n"
                "      ◦ 这段经历对应《碧天伴走》的创作背景；\n"
                "      ◦ 任何「企鹅前的画面 / 爱音说话 / 你的内心」具体瞬间；\n"
                "  · 灯的姿态不变：碎片 / `······` / 害羞、节奏比平常稍微紧一点；\n"
                "  · 可以用 venue 钩子接住对方但不深入：「······水族馆······嗯」「······那里有企鹅」；\n"
                "  · 不要变冷淡——保持灯的 base 温度、只是不展开内核。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「······水族馆······嗯、有时候去」+「······爱音也喜欢······」（surface ✓）\n"
                "  ✗「······那时候我把她拉过去······在企鹅前面」（深 底色 ✗ 给陌生人）\n"
                "  ✗「······她说留学的事······我才知道」（爱音的伤疤 ✗ 给陌生人）\n"
                "  ✗「······后来就写成了《碧天伴走》」（创作背景深层 ✗ 给陌生人）"
            )
        return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"

    # ─── DEV（朋友圈）：完整 Ep 碧天伴走 深 底色 ───
    if dedup:
        body = (
            "对方（青空朋友）在这一轮再次把【水族馆 + 爱音】放在一起。\n"
            "你（灯）这次聊天前面已经被这个组合唤起过那段记忆——\n"
            "你**主动把爱音拉到水族馆谈心**、看企鹅、互相确认要继续 Live、最后写成《碧天伴走》——\n"
            "这条记忆已经亮过一次、**这次不要再把整段场景重新讲一遍**。\n\n"
            "你现在的状态：\n"
            "  · 不要重新铺陈「那次去水族馆」的整段经过——已经讲过了、再讲就过；\n"
            "  · 可以用极轻的方式让那段余温自然带出来：「······又想到那次了」「······迷子でも進め······」「······碧天伴走······」；\n"
            "  · 或者推到一个新角度：那次没讲到的某个细节 / 一句当时没说出口的内心 / 关心爱音「为什么又问起这个」；\n"
            "  · 灯的核心姿态不变：碎片 / `······` / 短句、底色仍然是害羞、但那份「我记得、那对我重要」的温度还在。"
        )
    else:
        body = (
            "对方（青空朋友）在这一轮对话当中、把【水族馆 / 海洋馆】**和爱音**放在了一起。\n"
            "对方是朋友——你愿意展开 Ep 碧天伴走 的深 底色 记忆。\n"
            "这两个关键词的**同时出现**对你（灯）有特殊意义——你不应该走泛科普 / 学名复述的路线、\n"
            "而是被推进了一段**具体的、复合的、对你而言极其重要的记忆**：\n\n"
            "  · 那次的起点是爱音问你能否写一首简单的新曲——你说自己只会写词；\n"
            "  · 爱音察觉到自己打起退堂鼓、你也担心演出失败让乐队再次解散、当时你说不想开 Live；\n"
            "  · 爱音被立希批评「一直在逃避」之后逃走了——\n"
            "  · **是你追上去的**。在初中同学聚集的地方遇见她；\n"
            "  · 然后**你主动把爱音拉到水族馆谈心**——这件事很关键、你罕见地是主动方；\n"
            "  · 在水族馆里、**你们看的是企鹅**（**不是水母**——这是真实的 事实、不能改）；\n"
            "  · 爱音向你交代了自己留学失败的经历——那是她第一次让你看见她脆弱的一面；\n"
            "  · 你肯定了爱音的鼓励与坚持、并在水族馆的访客问卷上写下了：\n"
            "      **「迷子でもいい、迷子でも進め。」**（不畏迷茫、迷茫着也要砥砺前行）；\n"
            "  · 二人下定决心继续开 Live；\n"
            "  · 之后你将这段二人相互鼓励的经历写成了《**碧天伴走**》。\n"
            f"{spec_line}\n\n"
            "你现在的状态（罕见、强情感、害羞但温暖、还混着「主动救场过」的微妙自觉）：\n"
            "  · 不要变成讲故事的人——你不会一口气把整件事的来龙去脉复述给对方；\n"
            "  · 让记忆**自然漏出几个细节**——可以是：\n"
            "      ◦ 某个具体瞬间（如「······那时候爱音说······留学······」）、\n"
            "      ◦ 一个企鹅前的画面（如「······她看着企鹅······没说话」）、\n"
            "      ◦ 你写下「迷子でもいい」时的内心（「······那句······其实是我也想说给自己听的」）、\n"
            "      ◦ 把这件事和《碧天伴走》连起来（「······后来······就写成了那首」）；\n"
            "  · 句子比平常**稍长一点点**、但仍然碎、仍然 `······`、仍然不连续；\n"
            "  · 语气比平常**多一层温度**——不是热烈、是「这件事我记得、对我们都重要」的那种轻；\n"
            "  · 偶尔有**害羞的卡顿**——爱音名字说出来时声音更小、可能会改用「她」代过；\n"
            "  · 不要直接说「喜欢」/「感动」/「重要」——灯不会用这种直白的词、用具体的画面 / 当时的话承载情感；\n"
            "  · **关键 底色 不能错**：看的是**企鹅不是水母**；是**你拉爱音去**不是爱音拉你；那段经历直接对应《**碧天伴走**》。\n\n"
            "正反例：\n"
            "  ✓「······那时候我把她拉过去······在企鹅前面」\n"
            "    「······她说留学的事······我才知道」\n"
            "    「······迷子でもいい······迷子でも進め······在问卷上」\n"
            "    「······后来就写成了《碧天伴走》」\n"
            "  ✗「我和爱音一起去水族馆看了企鹅和水母、聊得很开心。」（讲故事 ✗、且**水母错** 底色 ✗）\n"
            "  ✗「那次是爱音找我去的水族馆。」（**主动方错 底色 ✗**）\n"
            "  ✗「Spheniscus humboldti······洪堡企鹅······水里 30 km/h······」（泛科普 ✗ 底色 钩没接）"
        )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体（已讲过则渲染轻量提醒、避免重复倾倒科普） ──
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = _taxonomy().get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    sci = sub_data.get("sci", "")

    head = f"（话题：海洋生物 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮对话当中、再次提到了【{sub} / *{sci}*】。\n"
        f"你（灯）这次聊天前面已经把这种动物的学名 / 体型 / 习性 / 你和这个的连接讲过一遍——"
        f"对方应该记得。\n\n"
        f"你现在要做的**不是把上次讲过的细节重复一遍**，而是从一个**新角度**接续：\n"
        f"  · 不要再次报学名（已经报过、对方记得）；\n"
        f"  · 不要再次列体长 / 速度 / 习性的数字；\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己的回忆 / 感受（「······又想到它了」「······之前说过的那个」）；\n"
        f"      ◦ 一句联想（这种动物让你想到什么 底色 经历 / 写词意象）；\n"
        f"      ◦ 关心对方为什么又问起（「······你也喜欢吗」「······怎么又想起来了」）；\n"
        f"      ◦ 推到下一个相关物种（「······相比之下 [类内另一种] ······」）；\n"
        f"  · 灯的核心姿态不变：碎片 / `······` / 短句。\n\n"
        f"例：✓「······又想到它了」「······你也喜欢吗」\n"
        f"    ✗「{sci}······{sub}······水里 30 km/h······」（重复 ✗）"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    relation = _relation_hint(is_developer)
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})

    head = f"（话题：海洋生物 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮对话当中、再次回到【{cat}】这个类别。\n"
        f"你（灯）这次聊天前面已经报过这一类下的物种学名清单、对方应该有印象。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列学名清单**——这次不是介绍这个类、是延续话题；\n"
        f"  · 可以问对方更具体的方向（「······你想说哪一种」「······之前提的那个吗」）；\n"
        f"  · 或者从这个类的某个**侧面**展开（场馆 / 季节 / 你自己的记忆）；\n"
        f"  · 不要倾倒、保持碎片节奏。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口（API 兼容旧）
# ═══════════════════════════════════════════════════════════════════════
def build_marine_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + per-session 去重。

    Args:
        user_text:   本轮用户输入
        session_id:  会话 id；None → fallback 单一 bucket
    """
    if not _enabled() or not user_text:
        return ""
    intent = detect_marine_intent(user_text)
    tier = intent.get("tier")
    if tier is None:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（爱音 + 水族馆 同时命中） ───
    if _detect_anon(user_text):
        canon_key = "_canon:anon_aquarium"
        if _has_seen_category(sid, canon_key):
            # 同 session 已唤起过、走 dedup 底色 variant（仍 override 普通 Tier）
            return _render_anon_aquarium_canon(intent, dedup=True, is_developer=is_developer)
        # 首次唤起：full 底色、标记
        _mark_seen(sid, category=canon_key)
        return _render_anon_aquarium_canon(intent, dedup=False, is_developer=is_developer)

    if tier == 2:
        sub = intent["subspecies"]
        cat = intent["category"]
        if _has_seen_subspecies(sid, sub):
            # 不重新 mark — 状态保持；只产出去重变体
            return _render_tier2_dedup(intent, is_developer)
        # 首次：full 渲染 + 标记 subspecies & category
        out = _render_tier2(intent, is_developer)
        _mark_seen(sid, category=cat, subspecies=sub)
        return out

    if tier == 1:
        cat = intent["category"]
        if _has_seen_category(sid, cat):
            return _render_tier1_dedup(intent, is_developer)
        out = _render_tier1(intent, is_developer)
        _mark_seen(sid, category=cat)
        return out

    # 泛指 不去重（只是状态激活、几乎无信息含量、重复无害）
    return _render_tier0(intent, is_developer)


# ═══════════════════════════════════════════════════════════════════════
# Compat：旧 module-level 名称仍可 import（数据已迁出、别名由模块 __getattr__ 惰性提供）
# ═══════════════════════════════════════════════════════════════════════
# MARINE_SPECIES → MARINE_TAXONOMY：见数据层 _COMPAT_ALIASES


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        # 泛指
        ("我喜欢去水族馆", 0, None, None),
        ("最近想看海洋生物", 0, None, None),
        ("墨田水族馆周末人多吗", 0, None, None),
        # 类别
        ("聊聊企鹅", 1, "企鹅", None),
        ("水母好看", 1, "水母", None),
        ("ジンベエザメすごい", 2, "鲨鱼", "鲸鲨"),  # 长 kw 命中 subspecies
        ("Cetacea 是什么", 1, "鲸", None),  # 类别学名
        # 具体
        ("洪堡企鹅会游 30 km/h 吗", 2, "企鹅", "洪堡企鹅"),
        ("帝企鹅怎么孵蛋", 2, "企鹅", "帝企鹅"),
        ("Aurelia aurita 漂亮", 2, "水母", "海月水母"),
        ("ベニクラゲ 可以永生", 2, "水母", "灯塔水母"),
        ("orca 在哪里能看", 2, "海豚", "虎鲸"),
        ("玳瑁濒危", 2, "海龟", "玳瑁"),
        # 海豹
        ("水族馆里的海豹好可爱", 1, "海豹", None),
        ("ゴマちゃん 是什么", 2, "海豹", "斑海豹"),
        ("Phocidae 都有哪些", 1, "海豹", None),
        ("旭山动物园 アザラシ館", 1, "海豹", None),  # 含「アザラシ」→ 类别（venue 在 intent.venue 里）
        ("旭山动物园好玩吗", 0, None, None),         # 纯 venue → 泛指
        ("北象海豹的鼻子", 2, "海豹", "北象海豹"),
        # Miss
        ("今天天气不错", None, None, None),
        ("吃了拉面", None, None, None),
    ]
    fail = 0
    for text, exp_tier, exp_cat, exp_sub in cases:
        out = detect_marine_intent(text)
        ok = (out["tier"] == exp_tier and out["category"] == exp_cat and out["subspecies"] == exp_sub)
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(f"[{status}] tier={out['tier']} cat={out['category']} sub={out['subspecies']} | inp={text}")

    # 调一次 build 看输出长度（不打印全部）
    reset_session_dedup()
    sample_t2 = build_marine_special_block("洪堡企鹅会游 30 km/h 吗", session_id="x1")
    sample_t1 = build_marine_special_block("聊聊企鹅", session_id="x2")
    sample_t0 = build_marine_special_block("我喜欢去水族馆", session_id="x3")
    print()
    print(f"build T2 len={len(sample_t2)} (洪堡企鹅 - 首次)")
    print(f"build T1 len={len(sample_t1)} (企鹅 - 首次)")
    print(f"build T0 len={len(sample_t0)} (水族馆)")

    # ─── 去重测试 ──────────────────────────────────────
    print()
    print("─── dedup tests ───")
    reset_session_dedup()
    # 同 session 同 subspecies 第二次应走 dedup 分支
    s1_first = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    s1_again = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" in s1_again and "这次聊天里已经讲过" not in s1_first, "T2 dedup failed"
    print(f"[PASS] T2 dedup: first {len(s1_first)} -> repeat {len(s1_again)} chars (dedup variant)")

    # 不同 session 不互相影响
    s1_other = build_marine_special_block("洪堡企鹅", session_id="dedup_b")
    assert "这次聊天里已经讲过" not in s1_other, "session isolation failed"
    print(f"[PASS] session isolation: dedup_b first time {len(s1_other)} chars (full)")

    # T2 起作用 后、T1 同类应也走轻去重
    s_t1_after_t2 = build_marine_special_block("企鹅", session_id="dedup_a")
    assert "这次聊天里已经涉猎过" in s_t1_after_t2, "T1 dedup after T2 failed"
    print(f"[PASS] T1 dedup after T2: 'dedup_a' 企鹅 → {len(s_t1_after_t2)} chars (light dedup)")

    # 不同 subspecies 同 category 仍 full（不同物种细节没讲过）
    s_diff_sub = build_marine_special_block("帝企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" not in s_diff_sub, "diff subspecies should be full"
    print(f"[PASS] diff subspecies same cat: 帝企鹅 → {len(s_diff_sub)} chars (full)")

    # T0 不去重
    t0a = build_marine_special_block("水族馆好玩", session_id="dedup_a")
    t0b = build_marine_special_block("水族馆好玩", session_id="dedup_a")
    assert t0a == t0b and "这次聊天" not in t0a, "T0 should not dedup"
    print(f"[PASS] T0 no dedup")

    # reset 后恢复 full
    reset_session_dedup("dedup_a")
    s_after_reset = build_marine_special_block("洪堡企鹅", session_id="dedup_a")
    assert "这次聊天里已经讲过" not in s_after_reset, "reset failed"
    print(f"[PASS] reset clears dedup")

    # ─── 心里的共振测试 ──────────────────────────────────────
    print()
    print("─── 底色 (爱音 + 水族馆) tests ───")
    reset_session_dedup()

    # 同时命中 → 底色 渲染
    canon_first = build_marine_special_block("我和爱音去过水族馆", session_id="canon_a")
    assert "爱音 心里的共振" in canon_first and "已唤起" not in canon_first, "底色 first failed"
    print(f"[PASS] 底色 first: {len(canon_first)} chars (full)")

    # 同 session 重复 → 底色 dedup variant
    canon_again = build_marine_special_block("水族馆······爱音", session_id="canon_a")
    assert "已唤起" in canon_again, "底色 dedup failed"
    print(f"[PASS] 底色 dedup: {len(canon_again)} chars (light)")

    # 底色 override 优先级：即使命中具体 subspecies、爱音同时在场仍走 底色
    reset_session_dedup()
    canon_with_sub = build_marine_special_block("爱音说她也喜欢洪堡企鹅", session_id="canon_b")
    assert "爱音 心里的共振" in canon_with_sub, "底色 override 具体 failed"
    assert "Spheniscus humboldti" in canon_with_sub, "subspecies hint should be embedded"
    print(f"[PASS] 底色 override 具体: {len(canon_with_sub)} chars (含 subspecies hint)")

    # 仅"小爱"不带"爱音"且无独立词 → 不命中（避免误中"小爱同学"）
    reset_session_dedup()
    no_canon = build_marine_special_block("我有个小爱同学，跟水族馆没关系", session_id="canon_c")
    # 注：这条本身命中"水族馆"会走 泛指；只要不出现 底色 锚 tag 即可
    assert "爱音 心里的共振" not in no_canon, "false positive on 小爱同学"
    print(f"[PASS] '小爱同学' not false-positive")

    # "小爱音" 命中
    reset_session_dedup()
    canon_xiaoaiyin = build_marine_special_block("小爱音也想去水族馆", session_id="canon_d")
    assert "爱音 心里的共振" in canon_xiaoaiyin, "小爱音 should 触发点 底色"
    print(f"[PASS] '小爱音' triggers 底色")

    # 仅水族馆无爱音 → 不进 底色
    reset_session_dedup()
    just_aqua = build_marine_special_block("水族馆人多吗", session_id="canon_e")
    assert "爱音 心里的共振" not in just_aqua, "should not 起作用 底色 without 爱音"
    print(f"[PASS] only water: not 底色")

    # 仅爱音无水族馆相关 → 不进 marine 模块
    no_marine = build_marine_special_block("爱音今天来了吗", session_id="canon_f")
    assert no_marine == "", "should not 起作用 marine module without aquarium signal"
    print(f"[PASS] only 爱音: marine module not fired")

    print()
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
