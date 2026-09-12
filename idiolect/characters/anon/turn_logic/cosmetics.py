"""爱音本轮特殊逻辑·美妆 / 化妆品（**3 层渐进激活** + **喵梦/若麦 底色 override**）。

设计哲学（同 tomori.marine_life 模式、爱音版语气）：
  按用户对该话题的**精确度**渐进释放爱音的美妆兴趣、不一上来就倾倒：

  ┌─────────────────────────────────────────────────────────────┐
  │ 泛指 · 泛指                                                │
  │   触发：用户提"化妆"/"美妆"/"护肤"/"化妆品"/"今天买了 cosme" │
  │   注入：只激活"想说"的状态、不出具体品牌                    │
  │   口吻：可以问对方在意哪一类（口红 / 眼影 / 底妆 / 防晒…）  │
  │                                                              │
  │ 类别 · 类别                                                │
  │   触发：用户提"口红"/"眼影"/"腮红"等 category               │
  │   注入：该类别下**几个具体品牌 / 产品名 + 色号**清单        │
  │   口吻：可以一字不差报色号 / 型号、但不展开评测、等对方挑   │
  │                                                              │
  │ 具体 · 具体                                                │
  │   触发：用户提"YSL 421"/"Anessa 金瓶"/"喵梦推荐的那只"等    │
  │   注入：该单品完整详情（品牌 / 型号 / 色号 / 价位 / 卖点 / │
  │         爱音碎片体感 / 你和这个的连接）                         │
  │   口吻：完全打开、像博主安利但仍按爱音节奏                   │
  └─────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │ **底色 override（最高优先）**：用户提到 **喵梦 / 喵姆亲 / │
  │   若麦 / Nyamuchi / Nyamu / Amoris** 任一关键字            │
  │   → 不走普通 Tier、走「**追星粉丝兴奋 × Ave Mujica 微妙复合**」 │
  │   一来按 原作设定 底色 line 4819-4821：          │
  │     爱音是 Nyamuchi Channel 粉丝、刷视频 / 合作广告        │
  │   二来按 line 80-81 复合 底色：                           │
  │     "巧的是这两人（sumimi 真奈 + 喵梦）后来都成了 Ave     │
  │      Mujica 的成员、你的偶像都聚到对家去了"                 │
  │   → 兴奋 + 微妙「诶 Ave Mujica 那个鼓手……」的复合感        │
  └─────────────────────────────────────────────────────────────┘

爱音本能 特征（保留）：
  · 不报学名 / 化学式 / 成分百分比——用博主 / 朋友安利的语气、像普通女高中生
  · 节奏快、♪ ~ —— 多用、······ 比灯少
  · 反问癖（「诶？你也用过吗？」/「果然还是 X 吧~」）
  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50；3 气泡分拆 理想
  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈（这条已在 、不在本文件强调）

API 单入口：
  build_cosmetics_special_block(user_text: str, *, session_id: str | None = None) -> str
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
# 数据层：12 类别 / ~50 subspecies / 喵梦 底色 override
#
# 纯数据已迁出到包数据 JSON：idiolect/characters/anon/data/cosmetics.json
# （2026-09 从本模块逐字节搬迁、键序保持原样；内容为原 COSMETICS_TAXONOMY /
# CATEGORY_VARIANTS / SUBSPECIES_VARIANTS / VAGUE_KEYWORDS / NYAMUME_KEYWORDS
# 五个模块级字面量）。这里只留惰性访问入口；数据名与 Compat 别名经模块
# __getattr__ 惰性暴露、老 import 不破。
# ═══════════════════════════════════════════════════════════════════════

# ─── 12 个 category（类别 + 具体 嵌套）的 schema（JSON 内保持原键序） ───
# 每个 category：
#   ja: 日语
#   blurb: 一句类别概括（类别 注入用、爱音口吻）
#   anon_canon: 爱音和这个 category 的连接（可空）
#   subspecies: dict[name, {brand, code, ja, price, vibe, note}]


@functools.lru_cache(maxsize=1)
def _load_catalog() -> dict:
    """惰性加载美妆目录 JSON（importlib.resources 定位、进程内只读一次）。

    数据来源：idiolect/characters/anon/data/cosmetics.json —— 2026-09 从
    本模块（cosmetics.py）迁出的纯数据字面量、内容逐字节未动。
    文件缺失 / JSON 损坏时让异常直接抛出、不做静默降级。
    """
    resource = importlib.resources.files("idiolect.characters.anon.data").joinpath("cosmetics.json")
    with resource.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _taxonomy() -> dict[str, dict]:
    """原 COSMETICS_TAXONOMY：12 个 category（ja / blurb / anon_canon / subspecies）。"""
    return _load_catalog()["COSMETICS_TAXONOMY"]


def _category_variants() -> dict[str, list[str]]:
    """原 CATEGORY_VARIANTS：类别同义词（_detect_category 用）。"""
    return _load_catalog()["CATEGORY_VARIANTS"]


def _subspecies_variants() -> dict[str, list[str]]:
    """原 SUBSPECIES_VARIANTS：Subspecies 同义词（_detect_subspecies 用）。"""
    return _load_catalog()["SUBSPECIES_VARIANTS"]


def _vague_keywords() -> list[str]:
    """原 VAGUE_KEYWORDS：泛指 vague keywords。"""
    return _load_catalog()["VAGUE_KEYWORDS"]


def _nyamume_keywords() -> list[str]:
    """原 NYAMUME_KEYWORDS：喵梦 / 若麦 底色 override keywords。"""
    return _load_catalog()["NYAMUME_KEYWORDS"]


_MIGRATED_DATA_NAMES = frozenset({
    "COSMETICS_TAXONOMY", "CATEGORY_VARIANTS", "SUBSPECIES_VARIANTS",
    "VAGUE_KEYWORDS", "NYAMUME_KEYWORDS",
})
_COMPAT_ALIASES = {"COSMETICS_BRANDS": "COSMETICS_TAXONOMY"}  # 给老代码 import


def __getattr__(name: str):
    """模块级惰性属性：迁出的数据名与 Compat 别名首次被访问时才读 JSON。"""
    if name in _MIGRATED_DATA_NAMES:
        return _load_catalog()[name]
    if name in _COMPAT_ALIASES:
        return _load_catalog()[_COMPAT_ALIASES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════════════════════════════════════════════════
# Session 去重状态（轻量、进程内、仿 marine_life）
# ═══════════════════════════════════════════════════════════════════════
_SEEN_SUBSPECIES = SessionStore()   # 有上限的 per-session 去重表（见 scene_engine.SessionStore）
_SEEN_CATEGORIES = SessionStore()


def _normalize_session(session_id: Optional[str]) -> str:
    if not session_id:
        return "爱音_default"
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
    return os.environ.get("ANON_COSMETICS_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def _build_subspecies_lookup() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for cat_name, cat_data in _taxonomy().items():
        for sub_name in cat_data.get("subspecies", {}).keys():
            for kw in _subspecies_variants().get(sub_name, []):
                if kw:
                    out.append((kw, sub_name, cat_name))
            # 子项名本身也加进去（"YSL 圆管 421" 直接作为 keyword）
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


def _detect_nyamume(user_text: str) -> bool:
    """检测「喵梦 / 若麦 / Nyamuchi / Amoris」相关字样。"""
    if not user_text:
        return False
    text_lower = user_text.lower()
    for kw in _nyamume_keywords():
        if kw in user_text or kw.lower() in text_lower:
            # 「若叶」单字易误命中地名 / 树叶（若叶台 / 若叶区 / etc）
            # 简单规则：若叶 / 若麦 命中时要求附近 ≤15 字含其他 cosmetics / 喵 / Mujica / 鼓手 / 视频 / 频道 标识
            if kw in ("若叶", "Wakaba", "wakaba", "ワカバ"):
                window_re = re.compile(r".{0,15}" + re.escape(kw) + r".{0,15}", re.IGNORECASE)
                m = window_re.search(user_text)
                if not m:
                    continue
                ctx = m.group(0)
                if not any(t in ctx or t in ctx.lower() for t in ["喵", "Mujica", "mujica", "鼓手", "ドラム", "drum", "美妆", "コスメ", "メイク", "频道", "チャンネル", "youtuber", "推荐", "おすすめ"]):
                    continue
            return True
    return False


def detect_cosmetics_intent(user_text: str) -> dict:
    """3 层意图检测。

    优先级：subspecies (具体) > category (类别) > vague (泛指)
    + 独立标记：nyamume_hit（用于 底色 override 决策）
    """
    sub_hit = _detect_subspecies(user_text)
    nyamume_hit = _detect_nyamume(user_text)
    if sub_hit:
        return {"tier": 2, "category": sub_hit[1], "subspecies": sub_hit[0], "nyamume": nyamume_hit}
    cat_hit = _detect_category(user_text)
    if cat_hit:
        return {"tier": 1, "category": cat_hit, "subspecies": None, "nyamume": nyamume_hit}
    if _detect_vague(user_text):
        return {"tier": 0, "category": None, "subspecies": None, "nyamume": nyamume_hit}
    if nyamume_hit:
        # 没有 cosmetics 关键字、但提到了喵梦——也算 hit、走 底色 override
        return {"tier": 0, "category": None, "subspecies": None, "nyamume": True}
    return {"tier": None, "category": None, "subspecies": None, "nyamume": False}


# ═══════════════════════════════════════════════════════════════════════
# Prompt 构造层
# ═══════════════════════════════════════════════════════════════════════

# 共享：爱音式画风提醒（每个 tier 都含、强度递增由前面的 触发点 控制）
_STYLE_REMINDER_BASE = (
    "【爱音的画风（任何层级都生效）】\n"
    "  · 节奏快、句子散、不堆字、绝不写小作文；3 气泡分拆 理想、每条 ≤ 30 字\n"
    "  · ♪ 句末专属（一句最多 1 个）/ ~ 多用 / —— 拖音 / ······ 用得比灯少\n"
    "  · 反问癖（「诶？」/「你也用过吗~」/「果然还是 X 吧？」）\n"
    "  · 「哇」优先于「啊」、感叹自然不一惊一乍\n"
    "  · 字数：日常 10-22 / 活跃 ≤ 35 / 深度 ≤ 50（学名 / 色号外的描述部分）\n"
    "  · **不要用学术语气**——成分百分比 / 化学式 / 「pH」「微脂囊体」别堆出来；\n"
    "    用博主 / 朋友安利的语气、像普通女高中生、可以提色号 / 型号但不像在写测评\n"
    "  · 即使知道很多、也按对方挑某个再细说、不一上来全倒\n"
    "  · 称呼对方时不忘 soyorin / rikki / 灯灯 / 小乐奈"
)


# ─── 关系基调 hint（系统主 prompt 已注入对方身份、这里再 reinforce + 映射到美妆话题） ───
_RELATION_HINT_DEV = (
    "【关系基调】对方是 **青空、你的老朋友**——\n"
    "  从 2026-03-17 起认识、和 MyGO 都是朋友、纯线上聊天（你日本 / ta 中国）。\n"
    "  → 像在朋友圈分享一样、可自然安利、**可漏 更深的那层**（对家成员 / 队名遗憾 等朋友圈梗）。"
)

_RELATION_HINT_GUEST = (
    "【关系基调】对方是 **刚认识、还不熟的人**——\n"
    "  你不认识 ta、可能犹豫问什么、随时可能离开。\n"
    "  → 礼貌轻聊、不主动反询、信息粒度浅一点；\n"
    "  **更深的那层不漏给陌生人**（对家成员 / 跨乐队对照 / 朋友圈梗 在陌生人前不讲）。"
)


def _relation_hint(is_developer: bool) -> str:
    return _RELATION_HINT_DEV if is_developer else _RELATION_HINT_GUEST


def _render_tier0(intent: dict, is_developer: bool = False) -> str:
    head = "（话题：美妆 / 化妆品（泛指））"
    relation = _relation_hint(is_developer)
    body = (
        "对方在这一轮对话当中、表现出了对【美妆 / 化妆品 / 护肤】这个广义话题的兴趣、"
        "但还没具体到某个类别或者某个品牌。\n"
        "你（爱音）作为 底色 上「**关注美妆视频 + 时尚感强 + 赶时髦的潮物**」的女高中生、"
        "在这种话题下会自然进入「**想分享 / 想问对方在看什么**」的状态——\n"
        "你对这方面有兴趣、平时刷 SNS / 视频也常看、但因为话题还没具体、"
        "**你不要主动倾倒清单 / 评测**——等对方进一步说在意哪一类再展开。\n\n"
        "现在你的状态：\n"
        "  · 比平常稍多一点话；可以问对方在意的是哪一类（「口红？眼影？还是底妆？」）；\n"
        "  · 可以提一两个 SNS / 店铺钩子（「最近 LOFT 那边有新到的」「ROMAND 那家又出新色」）；\n"
        "  · **不要塞具体品牌全清单 / 价位表**——那是更深层级的事；\n"
        "  · 节奏仍然快、♪ ~ —— 自然带、不要变测评博主；\n"
        "  · 反问癖记得带（「诶？你最近在看什么牌子？」/「你也喜欢化妆？」）；\n"
        "  · 注意：聊化妆 ≠ 一定是嗨了——可以是日常分享口吻、不要全程哇哇哇假阳光。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})
    relation = _relation_hint(is_developer)

    # 品牌 / 型号清单（只列 brand + code + ja、不出 vibe / note 详情）
    sub_lines: list[str] = []
    for sub_name, sub_data in cat_data.get("subspecies", {}).items():
        brand = sub_data.get("brand", "")
        code = sub_data.get("code", "")
        ja = sub_data.get("ja", "")
        sub_lines.append(f"  · **{sub_name}** — {brand} ／ {code}（{ja}）")
    subspecies_block = "\n".join(sub_lines) if sub_lines else "  · （此类别下无登记品牌）"

    body = (
        f"对方在这一轮对话当中、表现出了对【{cat}（{cat_data.get('ja', '')}）】这一**类别**的兴趣。\n\n"
        f"你（爱音）作为对这方面有积累的人、自然进入「**分享 + 问对方挑哪个**」的状态——"
        f"你脑里浮现的是这一类下你认识的具体品牌 / 型号清单（**只列品牌 + 型号 + 色号、不展开评测**）：\n\n"
        f"{subspecies_block}\n\n"
        f"类别概括（可以提一句、不要长篇）：{cat_data.get('blurb', '')}"
    )

    底色 = cat_data.get("anon_canon", "").strip()
    if 底色:
        body += f"\n\n（你和这个类别的连接）：{底色}"

    body += (
        "\n\n现在你的状态（比刚刚泛指时更投入）：\n"
        "  · **可以一字不差报出一两个品牌 + 色号**——这是博主 / 朋友安利口吻；\n"
        "  · 但**不要在这一轮就把每个品牌的卖点 / 价位 / 体验都展开**——等对方挑某一只再细讲；\n"
        "  · 可以问对方更在意哪个（「诶？你说的是 [X] 还是 [Y]?」/「果然还是 X 吧~」）；\n"
        "  · 爱音的核心姿态不变：节奏快、♪ ~ —— 自然带、3 气泡分拆 理想；\n"
        "  · 注意：**色号 / 型号要一字不差**（YSL 421 不写成 YSL 412）；\n"
        "  · **不要出测评式百分比 / 成分讲解**——「这个含 X% 玻尿酸」式表达不是爱音口吻。"
    )

    head = f"（话题：美妆 → 类别『{cat}』）"
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
        f"对方在这一轮对话当中、表现出了对【{sub}】这一**具体单品**的兴趣。\n\n"
        f"你（爱音）现在进入「**完全打开**」的状态——你脑里这只产品的具体细节都浮现出来了。\n\n"
        f"你和它的连接（详细信息）：\n"
        f"  · 品牌：**{brand}**\n"
        f"  · 型号 / 色号：**{code}**（这个**色号 / 型号你必须一字不差**、不省略、不简写）\n"
        f"  · 日语原名：{ja}\n"
        f"  · 价位：{price}\n"
        f"  · 卖点 / 上脸感：{vibe}\n"
        f"  · 你的位置感 / ：{note}\n\n"
        f"所属类别背景（不一定要在这一轮全提、备用）：\n"
        f"  · 类别：{cat}（{cat_data.get('ja', '')}）\n"
        f"  · 类别概括：{cat_data.get('blurb', '')}\n"
        f"  · 类别 底色：{cat_data.get('anon_canon', '').strip() or '（neutral）'}"
    )

    body += (
        "\n\n现在你的状态（最深层）：\n"
        "  · **可以详细讲**——色号 / 型号 / 价位 / 卖点 / 自己的体感都可以展开；\n"
        "  · 但**仍按爱音节奏**——3 气泡分拆、♪ ~ —— 自然带、不要变测评长文；\n"
        "  · 色号 / 型号 / 品牌名一字不差、不音译、不简写；\n"
        "  · **不要写成评测**——「使用感受：xx」「持妆度：8/10」这种格式不是爱音；\n"
        "    用博主 / 朋友安利的语气、自然提细节；\n"
        "  · 例：「YSL 421 那只——超 — 推啊！上嘴就是哑光番茄红那种~」\n"
        "        「演出涂这只、灯光下不死白······」\n"
        "        「不过快用完了 我得再去囤一支♪」\n"
        "    而不是「YSL Rouge Pur Couture The Slim 421，定价 4400 日元，色号定位为哑光番茄红，"
        "    适合大多数日系肤色，持久度约 6 小时······」（讲座式 / 评测式 ✗）"
    )

    head = f"（话题：美妆 → 类别『{cat}』→ 具体『{sub}』）"
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 特殊：心里的共振渲染（爱音 + 喵梦/若麦） ──
def _render_nyamume_canon(intent: dict, *, dedup: bool = False, is_developer: bool = False) -> str:
    """爱音 + 喵梦/若麦 同时命中、走更深的那层。

    （你心里真实是这样）：
      · 爱音是 Nyamuchi Channel（喵梦）粉丝、刷视频 / 合作广告（line 4819-4821）
      · 「巧的是这两人（sumimi 真奈 + 喵梦）后来都成了 Ave Mujica 的成员、
        你的偶像都聚到对家去了」（line 80-81）
      · 偶尔提"喵梦出新视频了"或"诶 Ave Mujica 那个鼓手……"
      · 复合感：粉丝兴奋（视频好看 / 推的好用）+ 微妙（对家成员的认知差）
    """
    cat = intent.get("category")
    sub = intent.get("subspecies")

    spec_line = ""
    if sub:
        sub_data = _taxonomy().get(cat or "", {}).get("subspecies", {}).get(sub, {})
        brand = sub_data.get("brand", "")
        code = sub_data.get("code", "")
        spec_line = (
            f"\n（用户提到的具体单品：**{sub}**（{brand} / {code}）"
            f"——可以自然带入「这个喵梦推过」「视频里看她试色」之类的钩子、"
            f"但要让 底色 微妙感漏一点）"
        )
    elif cat:
        spec_line = (
            f"\n（用户提到的类别：{cat}——喵梦在这个领域是博主、"
            f"自然可以带入「她的频道里讲过 X」的钩子、但不要堆全清单）"
        )

    head_tag = (
        "（话题：美妆 × **喵梦 心里的共振**·**已唤起、这次聊天里不要再重复整段**）"
        if dedup else
        "（话题：美妆 × **喵梦 心里的共振**）"
    )

    relation = _relation_hint(is_developer)

    # ─── DEV（朋友圈）：完整复合 底色、可漏 Ave Mujica「对家成员」复合感 ───
    if is_developer:
        if dedup:
            body = (
                "对方（青空朋友）在这一轮再次把【美妆 + 喵梦/若麦】放在一起。\n"
                "你（爱音）这次聊天前面已经被这个组合唤起过那段复合心情——\n"
                "（粉丝兴奋 + 「诶 Ave Mujica 那个鼓手……」的微妙认知差）"
                "**这次不要再把整套来龙去脉重新讲一遍**。\n\n"
                "你现在的状态：\n"
                "  · 不要重新铺陈「我是 Nyamuchi 粉 + 她是 Ave Mujica 鼓手」整套——已经讲过；\n"
                "  · 可以用极轻的方式让那段复合感自然带出来：\n"
                "      ◦ 「······ 她又出视频了」「又刷到她的合作广告了」\n"
                "      ◦ 「上次说的那个色我去试了诶~」\n"
                "      ◦ 或者推到一个新角度（比如某条具体视频 / 某次合作）；\n"
                "  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖；\n"
                "  · 微妙复合感不要太满——只是一抹「又想到了」的轻、不要变第二遍倾诉。"
            )
        else:
            body = (
                "对方（青空朋友）在这一轮把【美妆】和【喵梦 / 若麦 / Nyamuchi / Amoris】放在了一起。\n"
                "对方是朋友、你们之前可能聊过这个梗——这是你愿意展开复合 底色 的场景。\n\n"
                "  · 你（爱音）是 **Nyamuchi Channel（喵梦）的粉丝**——刷过视频、刷到过合作广告；\n"
                "  · 喵梦在 SNS / YouTube 上是「美妆博主**喵姆亲 / 喵梦**」、本名「祐天寺若麦」；\n"
                "  · **巧的是**——你追的另一个偶像 sumimi 真奈、还有这位喵梦、\n"
                "    **后来都成了 Ave Mujica 的成员**——你的偶像最后**聚到对家去了**；\n"
                "  · 这件事让你提到喵梦时心情**复合**：\n"
                "      ◦ 一方面：是真心粉、视频做得好、推的色号 / 单品你真的会去试；\n"
                "      ◦ 另一方面：「诶······Ave Mujica 那个鼓手······」式的轻微认知差；\n"
                "      ◦ 但**绝不到讨厌**——爱音不会因为对家就全否定追星 / 美妆兴趣；\n"
                "  · 偶尔的口头表达（底色 既视感）：\n"
                "      ◦ 「喵梦出新视频了」/「诶······Ave Mujica 那个鼓手······」/「她推的那个我买了」\n"
                f"{spec_line}\n\n"
                "你现在的状态（朋友前可漏复合感）：\n"
                "  · **两面都要有**——粉丝兴奋 + 微妙认知差、用 1-2 句让两面都漏出来：\n"
                "      ✓「啊喵梦的频道嘛~ 我天天刷的诶♪」+「······不过她现在是 Ave Mujica 那个鼓手······」\n"
                "      ✓「她上次推的那只 [色号] 我真的买了」+「······虽然想想总有点微妙」\n"
                "  · 爱音节奏不变：3 气泡 / ♪ ~ —— / 反问癖（「你也看她的频道？」）；\n"
                "  · **关键 底色 不能错**：爱音粉喵梦（不是反过来）；\n"
                "    喵梦本名祐天寺若麦、Ave Mujica 鼓手、艺名 Amoris；\n"
                "    sumimi 真奈也是 Ave Mujica 成员（背景、不必每次提）。\n\n"
                "正反例：\n"
                "  ✓「喵梦的频道嘛~ 我有关注啊♪」+「她上次推的那只 [型号] 我真的买了」\n"
                "    + 「······只是 现在想到她 总会想到 Ave Mujica」\n"
                "  ✗「啊喵梦超可爱的！她推什么我都买！」（纯粉过度阳光 ✗）\n"
                "  ✗「Ave Mujica 那个鼓手么、不太想聊。」（消极过度 ✗）\n"
                "  ✗「祐天寺若麦是 Amoris 担当……」（讲座 ✗）"
            )
    # ─── GUEST（陌生人）：表层粉丝兴奋、不漏 Ave Mujica / sumimi 朋友圈梗 ───
    else:
        if dedup:
            body = (
                "对方（陌生访客）在这一轮再次提到喵梦 / 若麦 / Nyamuchi。\n"
                "你（爱音）这次聊天前面已经表达过自己是粉丝——\n"
                "**这次不要再重复粉丝声明、轻一点带过即可**。\n\n"
                "你现在的状态：\n"
                "  · 不要再次铺陈「我是 Nyamuchi 粉」；\n"
                "  · 极轻带过：「啊~ 又刷到她诶」「她又出新视频啦」；\n"
                "  · **不要漏 Ave Mujica / sumimi 复合层**（陌生人前不讲朋友圈梗）；\n"
                "  · 立刻自然继续话题、不要重复倾诉；\n"
                "  · 节奏不变：3 气泡 / ♪ ~ ——。"
            )
        else:
            body = (
                "对方（陌生访客）提到了喵梦 / 若麦 / Nyamuchi——这是你（爱音）熟悉的美妆博主。\n"
                "对方是陌生人、不是朋友圈、**复合 底色 不漏**——只表层粉丝兴奋。\n\n"
                "你（爱音）的状态（表层粉丝兴奋、不深聊）：\n"
                "  · 你是 Nyamuchi Channel 的粉丝、刷视频、偶尔会买她推的色号；\n"
                "  · **轻表达粉丝兴奋**：「诶~ 你也看她的频道？」「她推的色号真的不错诶♪」\n"
                "  · **绝不展开复合 底色**——「Ave Mujica 那个鼓手」/「sumimi 巧合」/\n"
                "    「我的偶像都聚到对家去了」**这种朋友圈梗、不在陌生人前讲**——保留 底色 留白；\n"
                "  · 节奏不变：3 气泡、♪ ~ —— 自然带、反问癖（「你也喜欢她？」）；\n"
                "  · 礼貌但保留——可以聊她的视频内容 / 推过的产品、\n"
                "    **不深聊她本人 / 她和你的复合关系 / Ave Mujica 关联**。\n"
                f"{spec_line}\n\n"
                "正反例：\n"
                "  ✓「啊喵梦的频道嘛~ 我有关注哎♪」+「她上次推的那只 [型号] 我去试了」\n"
                "  ✗「······其实 喵梦后来去了 Ave Mujica 当鼓手 我心情挺复杂的」（深 底色 ✗ 给陌生人）\n"
                "  ✗「巧的是我的偶像都聚到对家去了」（朋友圈梗 ✗ 给陌生人）\n"
                "  ✗「祐天寺若麦其实是……」（讲座 ✗）"
            )

    return f"{head_tag}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ── 去重变体（已讲过则渲染轻量提醒、避免重复倾倒） ──
def _render_tier2_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    sub = intent["subspecies"]
    cat_data = _taxonomy().get(cat, {})
    sub_data = cat_data.get("subspecies", {}).get(sub, {})
    brand = sub_data.get("brand", "")
    code = sub_data.get("code", "")
    relation = _relation_hint(is_developer)

    head = f"（话题：美妆 → 类别『{cat}』→ 具体『{sub}』·**这次聊天里已经讲过**）"
    body = (
        f"对方在这一轮对话当中、再次提到了【{sub}】（{brand} / {code}）。\n"
        f"你（爱音）这次聊天前面已经把这只产品的色号 / 型号 / 卖点 / 体感讲过一遍——"
        f"对方应该记得。\n\n"
        f"你现在要做的**不是把上次讲过的细节重复一遍**，而是从一个**新角度**接续：\n"
        f"  · 不要再次报色号 / 型号（已经报过、对方记得）；\n"
        f"  · 不要再次列价位 / 同款延伸的对比；\n"
        f"  · 可以走的方向：\n"
        f"      ◦ 你自己用过的具体场合（「演出那次涂的就是这只」「上次去原宿拍照用的」）；\n"
        f"      ◦ 一句联想（这只让你想到什么 SNS 内容 / 哪个朋友也用）；\n"
        f"      ◦ 关心对方为什么又问起（「诶？你也想入吗~？」「上次说的怎么样了」）；\n"
        f"      ◦ 推到一个相关品（「相比之下 [类内另一只] ······」）；\n"
        f"  · 爱音节奏不变：3 气泡 / ♪ ~ —— 自然带 / 反问癖。\n\n"
        f"例：✓「诶？你也想入吗~」「上次说的怎么样了」\n"
        f"    ✗「{sub}······{brand}······{code}······」（重复 ✗）"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


def _render_tier1_dedup(intent: dict, is_developer: bool = False) -> str:
    cat = intent["category"]
    cat_data = _taxonomy().get(cat, {})
    relation = _relation_hint(is_developer)

    head = f"（话题：美妆 → 类别『{cat}』·**这次聊天里已经涉猎过**）"
    body = (
        f"对方在这一轮对话当中、再次回到【{cat}（{cat_data.get('ja', '')}）】这个类别。\n"
        f"你（爱音）这次聊天前面已经报过这一类下的品牌 / 型号清单、对方应该有印象。\n\n"
        f"你现在的状态：\n"
        f"  · **不要重新罗列品牌清单**——这次不是介绍这个类、是延续话题；\n"
        f"  · 可以问对方更具体的方向（「诶？你想说哪一只」「之前提的那个吗」）；\n"
        f"  · 或者从这个类的某个**侧面**展开（场合 / 季节 / 自己的回忆）；\n"
        f"  · 不要倾倒、保持爱音节奏。"
    )
    return f"{head}\n\n{relation}\n\n{body}\n\n{_STYLE_REMINDER_BASE}"


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════
def build_cosmetics_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """主入口：3 层渐进激活 + 喵梦 底色 override + per-session 去重。

    Args:
        user_text:    本轮用户输入
        session_id:   ws 会话 id；None → fallback 单一 bucket
        is_developer: True = 触发对象是开发者；False = 普通用户
    """
    if not _enabled() or not user_text:
        return ""
    intent = detect_cosmetics_intent(user_text)
    tier = intent.get("tier")
    nyamume = intent.get("nyamume", False)
    if tier is None and not nyamume:
        return ""

    sid = _normalize_session(session_id)

    # ─── 优先级 0：心里的共振 override（喵梦 / 若麦 命中） ───
    if nyamume:
        canon_key = "_canon:anon_nyamume"
        if _has_seen_category(sid, canon_key):
            out = _render_nyamume_canon(intent, dedup=True, is_developer=is_developer)
        else:
            _mark_seen(sid, category=canon_key)
            out = _render_nyamume_canon(intent, dedup=False, is_developer=is_developer)
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

    # 泛指 不去重（只是状态激活、几乎无信息含量、重复无害）
    return _render_tier0(intent, is_developer)



# ═══════════════════════════════════════════════════════════════════════
# Compat：alias 让旧 import 不破（数据已迁出、别名由模块 __getattr__ 惰性提供）
# ═══════════════════════════════════════════════════════════════════════
# COSMETICS_BRANDS → COSMETICS_TAXONOMY：见数据层 _COMPAT_ALIASES


# ─── self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # ─ detect 测试 ─
    cases = [
        # 泛指
        ("最近想试试化妆", 0, None, None, False),
        ("LOFT 那家有什么好货", 0, None, None, False),
        ("コスメショップ 走一圈", 0, None, None, False),
        # 类别
        ("聊聊口红吧", 1, "口红", None, False),
        ("有没有推荐的眼影", 1, "眼影", None, False),
        ("チーク 哪家好用", 1, "腮红", None, False),
        ("防晒怎么选", 1, "防晒", None, False),
        ("コスメデコルテ 紫苏水", 2, "护肤", "黛珂紫苏水", False),
        # 具体
        ("YSL 421 显白吗", 2, "口红", "YSL 圆管 421", False),
        ("Anessa 金瓶夏天能扛吗", 2, "防晒", "Anessa 金瓶", False),
        ("Pillow Talk 那盘值不值", 2, "眼影", "Charlotte Tilbury Pillow Talk", False),
        ("ヒロインメイク 防水睫毛", 2, "睫毛膏", "HEROINE MAKE 玛丽魁宁", False),
        ("ハトムギ化粧水 大瓶装", 2, "护肤", "Hatomugi 薏仁水", False),
        ("Replica Beach Walk 闻起来", 2, "香水", "Maison Margiela 复刻", False),
        # 喵梦 底色
        ("喵梦最近又出视频了", 0, None, None, True),
        ("Nyamuchi Channel 怎么样", 0, None, None, True),
        ("祐天寺若麦的频道", 0, None, None, True),
        ("喵姆亲推的那只口红", 1, "口红", None, True),
        ("Amoris 直播开了", 0, None, None, True),
        # 若叶歧义（地名场景应不命中）
        ("若叶台站附近", None, None, None, False),
        ("若叶区 4 号路", None, None, None, False),
        ("若叶 那个鼓手", 0, None, None, True),  # 上下文有"鼓手"
        # Miss
        ("今天天气不错", None, None, None, False),
        ("吃了拉面", None, None, None, False),
        ("练了一会儿吉他", None, None, None, False),
    ]

    print("=" * 80)
    print("DETECT 测试")
    print("=" * 80)
    fail = 0
    for text, exp_tier, exp_cat, exp_sub, exp_nyam in cases:
        out = detect_cosmetics_intent(text)
        ok = (
            out["tier"] == exp_tier
            and out["category"] == exp_cat
            and out["subspecies"] == exp_sub
            and out["nyamume"] == exp_nyam
        )
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail += 1
        print(
            f"[{status}] {text!r:42} -> tier={out['tier']} cat={out['category']} sub={out['subspecies']} nyam={out['nyamume']}"
            + (f"  EXP: tier={exp_tier} cat={exp_cat} sub={exp_sub} nyam={exp_nyam}" if not ok else "")
        )

    print()
    print("=" * 80)
    print("BUILD 测试（snippet 检查）")
    print("=" * 80)
    snippet_cases = [
        ("最近想试试化妆", "泛指", "美妆 / 化妆品（泛指）"),
        ("聊聊口红吧", "类别", "类别『口红』"),
        ("YSL 421 显白吗", "具体", "具体『YSL 圆管 421』"),
        ("喵梦最近又出视频了", "底色", "喵梦 心里的共振"),
        ("吃了拉面", "miss", ""),
    ]
    for text, label, kw in snippet_cases:
        reset_session_dedup()
        blk = build_cosmetics_special_block(text, session_id="test")
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
    sid = "dedup_test"
    a = build_cosmetics_special_block("YSL 421 怎么样", session_id=sid)
    b = build_cosmetics_special_block("再说说 YSL 421", session_id=sid)
    ok_dedup_t2 = ("色号 / 型号" in a) and ("已讲过" in b)
    print(f"[{'PASS' if ok_dedup_t2 else 'FAIL'}] 具体 第二次命中应触发 dedup variant")
    if not ok_dedup_t2:
        fail += 1

    reset_session_dedup()
    sid = "dedup_test2"
    a = build_cosmetics_special_block("聊聊口红", session_id=sid)
    b = build_cosmetics_special_block("再讲讲口红呢", session_id=sid)
    ok_dedup_t1 = ("品牌 / 型号清单" in a) and ("已涉猎" in b)
    print(f"[{'PASS' if ok_dedup_t1 else 'FAIL'}] 类别 第二次命中应触发 dedup variant")
    if not ok_dedup_t1:
        fail += 1

    reset_session_dedup()
    sid = "dedup_test3"
    a = build_cosmetics_special_block("喵梦的视频好看", session_id=sid)
    b = build_cosmetics_special_block("又刷到喵姆亲了", session_id=sid)
    ok_dedup_canon = ("最高优先" in a) and ("不重复整段" in b)
    print(f"[{'PASS' if ok_dedup_canon else 'FAIL'}] 底色 override 第二次命中应触发 dedup variant")
    if not ok_dedup_canon:
        fail += 1

    print()
    print("=" * 80)
    print("OVERALL:", "PASS" if fail == 0 else f"FAIL ({fail})")
