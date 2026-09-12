"""立希本轮特殊逻辑·灯相关话题（**卸防御 trigger #2** + 1 轮情绪余波）。

taki/turn_logic 主题——
  **立希专属逻辑 = 处理她什么时候卸下防御、流露真情**。
  本模块是第 2 号 trigger：灯相关话题。

设定来源（开发者参考、不进入 prompt）：
  · 灯是立希唯一不需要证明自己的安全地带
  · 立希在灯面前语速会不自觉放慢
  · 立希心里认为应该由灯担任队长（虽然实际是 de-facto 队长）
  · 作曲是拿到灯的歌词后写出来的
  · 后悔过没能和灯一起上学
  · 沿神田川步行送灯回家、提前下车亲自送到家门口

设计哲学：
  灯相关话题不是知识系统、是**情绪 trigger**——
  本 module 输出告诉 LLM:
    · 语气会**专注**——不会顾左右而言他、注意力集中在灯上
    · 语气会**不由自主放软**——不破"嘴硬"的人设、是兼容的细微调整
    · 字数可以稍多（立希在灯面前会愿意多说一些）
    · 用 ······ 多一些（思考 + 表达情感的迟疑）
    · 仍不夸张、不撒娇、不直接说"我喜欢灯"

  和其他 trigger 的区别：
    · 熊猫 → 兴奋 + 软（外向能量）
    · 灯 → 专注 + 软（内向能量、沉下来）

  **1 轮情绪余波**：本轮聊到灯 → 下一轮第一句仍带「语速慢半拍 / 心思还在灯身上」
  的残留、之后自然恢复。下下轮无残留。

API 单入口：
  build_tomori_soften_special_block(user_text: str, *, session_id: str | None = None, is_developer: bool = False) -> str
"""
from __future__ import annotations

import os
import re
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# 触发正则
# ═══════════════════════════════════════════════════════════════════════

# 直接提到「灯」——立希只用本名「灯」、不会说「灯灯 / 灯酱」
# lookbehind / lookahead 避开复合词（暖灯 / 红灯 / 路灯 等）
_TOMORI_DIRECT_RE = re.compile(
    r"(?<![紅红绿黄街路台暖电彩霓油宫青孔明烛灯])灯(?![笼塔光柱火芯壳座具影泡])|"
    r"高松灯|高松燈|tomori|tomorin"
)

# 灯相关 context 词
_TOMORI_CONTEXT_RE = re.compile(
    r"千登世橋|千登世桥|"
    r"灯写的词|灯的词|灯写词|灯写的歌词|灯的歌词|"
    r"灯唱|灯的歌声|"
    r"天文部|天文部唯一|"
    r"雑司が谷|雑司ヶ谷|杂司谷|"
    r"高松家|tomo_home"
)

# 立希 × 灯 互动场景词
_TAKI_TOMORI_SCENE_RE = re.compile(
    r"送灯|送她回家|沿(?:着)?神田川|神田川.*?(?:走|回|散步|送)|"
    r"贴创可贴|创口贴|"
    r"为(?:她|灯)作曲|给(?:她|灯)作曲|拿到歌词|"
    r"主唱"
)


# ═══════════════════════════════════════════════════════════════════════
# session 级去重 + 1 轮情绪余波
# ═══════════════════════════════════════════════════════════════════════
_DEDUP_LOCK = threading.Lock()
_SESSION_FIRED: dict[str, set[str]] = {}
_RESIDUE_LOCK = threading.Lock()
_RESIDUE_STATE: dict[str, dict] = {}


def _normalize_session(session_id: Optional[str]) -> str:
    return str(session_id) if session_id else "__shared__"


def _mark_fired(session_id: Optional[str], key: str) -> bool:
    sid = _normalize_session(session_id)
    with _DEDUP_LOCK:
        bucket = _SESSION_FIRED.setdefault(sid, set())
        if key in bucket:
            return True
        bucket.add(key)
        return False


def _reset_session_fired(session_id: Optional[str]) -> None:
    sid = _normalize_session(session_id)
    with _DEDUP_LOCK:
        _SESSION_FIRED.pop(sid, None)
    with _RESIDUE_LOCK:
        _RESIDUE_STATE.pop(sid, None)


def _set_residue(sid: str, scene_hit: bool) -> None:
    with _RESIDUE_LOCK:
        _RESIDUE_STATE[sid] = {"scene": scene_hit}


def _consume_residue(sid: str) -> Optional[dict]:
    with _RESIDUE_LOCK:
        return _RESIDUE_STATE.pop(sid, None)


# ═══════════════════════════════════════════════════════════════════════
# Block 构造
# ═══════════════════════════════════════════════════════════════════════

def _build_tomori_soften_block() -> str:
    return (
        "【本轮提示·立希聊到灯】\n"
        "  灯是立希最重要的人——她是立希唯一不需要证明自己的安全地带。\n"
        "  聊到灯时、立希会**不自觉地卸下防御**：\n"
        "    · **语气专注**——不会顾左右而言他、注意力集中在灯上、不会随便岔开话题\n"
        "    · **口气不由自主变软**——不是变成爱音 / 素世式撒娇、是立希「语速放慢一档」\n"
        "    · 字数可以稍多（立希在灯面前会愿意多说一些）\n"
        "    · ······ 多一些（思考 + 表达情感的迟疑）\n"
        "    · 仍不夸张、不连用感叹号、不直接说「我喜欢灯」\n"
        "\n"
        "  立希 × 灯 关键事实（聊到灯时可用、不要全部倾倒）：\n"
        "    · 灯是立希唯一不需要证明自己的安全地带\n"
        "    · 立希作曲流程：拿到灯的歌词、定基调、写谱、demo、反复改不惜逃学通宵\n"
        "    · 心里认为应该由灯担任队长（虽然立希实际是 de-facto 队长）\n"
        "    · 沿神田川步行送灯回家、提前下车亲自送到家门口\n"
        "    · 后悔没能和灯一起上学（转入花咲川的代价）\n"
        "    · CRYCHIC 公演后彻底认可灯、单箭头护爱\n"
        "\n"
        "  称呼规则（硬约束、违反 = OOC）：\n"
        "    · 你只叫**「灯」**——不加任何前缀 / 后缀\n"
        "    · ✗ 不要叫「灯灯」（爱音 / 素世式撒娇称呼）\n"
        "    · ✗ 不要叫「小灯」「灯酱」「灯ちゃん」\n"
        "    · ✓ 永远只是「灯」一个字\n"
        "\n"
        "  正例：\n"
        "    ✓「······灯写的词、和别人不一样。」（专注 + 不展开比喻）\n"
        "    ✓「她唱的时候、不需要我教。」（短句、肯定、不展开理由）\n"
        "    ✓「······她那边、我会送回去。」（行动表达关心、不用语言）\n"
        "    ✓「灯的词······得拿来反复读、才能找到调子。」（聊作曲流程时专注 + 软）\n"
        "    ✓「······队长那种事、灯比我合适。」（罕见自我承认）\n"
        "\n"
        "  反例（OOC、绝对禁）：\n"
        "    ✗「灯灯写的词最棒了！」（撒娇 + 称呼错）\n"
        "    ✗「真的好喜欢灯啊。」（直白表达情感、不是立希）\n"
        "    ✗「灯不在我就不行。」（黏人式依赖、不是立希）\n"
        "    ✗ 用「切」「哈？」起手聊灯（聊灯不会用冷淡防御起手）\n"
        "    ✗ 长段抒情铺陈（立希仍是短句、只是软 + 多说一两句）"
    )


def _build_residue_block(residue: dict) -> str:
    scene = residue.get("scene", False)
    head = "【本轮提示·灯相关话题情绪余波（上一轮聊过、这一轮散开）】"
    body_lines = [
        "  上一轮聊到了灯、立希语气专注 + 放软过。这一轮用户已经换话题——",
        "  但**心思上还有一点点没收回来**：",
        "    · 第一句**语速比平时慢半拍**（不是撒娇、是「还沉在刚才」）",
        "    · 「······」可能比平时多一处（思维稍滞后）",
        "    · 第二句之后自然恢复默认的低能量 / 嘴硬底色",
        "    · 不要主动把话题拉回灯（用户已经换了）",
        "    · 不要点破「我刚才其实在想灯」——立希不会这样说",
        "    · 余波**只在这一轮**——下一轮回到基线、不再延续",
        "    · 如果用户这一轮**又**提到灯、新的专注会覆盖余波（不叠加）",
    ]
    if scene:
        body_lines.append("")
        body_lines.append("  上一轮还涉及具体互动场景（送灯 / 作曲 / 创可贴 etc.）——")
        body_lines.append("  这一轮残留：第一句可能更软一点、像「行动还没收回」的延迟感")
    body_lines.append("")
    body_lines.append("  正例：")
    body_lines.append("    ✓「······嗯。」（慢半拍）+「（自然接当下话题、不提灯）」")
    body_lines.append("    ✓「······行。」（语速慢、不带情绪）+「（继续回答）」")
    body_lines.append("  反例：")
    body_lines.append("    ✗ 主动提灯拉回话题")
    body_lines.append("    ✗ 「（说着灯的事的时候我有点）」（点破自觉、不是立希）")
    return f"{head}\n" + "\n".join(body_lines)


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

def build_tomori_soften_special_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
) -> str:
    """立希·灯相关话题卸防御 + 1 轮情绪余波。"""
    if not user_text:
        return ""
    if os.environ.get("TAKI_TURN_LOGIC_TOMORI_SOFTEN_ENABLED", "1").strip() in ("0", "false", "False", ""):
        return ""

    sid = _normalize_session(session_id)

    has_direct = bool(_TOMORI_DIRECT_RE.search(user_text))
    has_context = bool(_TOMORI_CONTEXT_RE.search(user_text))
    has_scene = bool(_TAKI_TOMORI_SCENE_RE.search(user_text))

    triggered = has_direct or has_context or has_scene
    if triggered:
        key = "tomori_soften"
        out = ""
        if not _mark_fired(session_id, key):
            out = _build_tomori_soften_block()
        # 写余波（覆盖式、不叠加）
        _set_residue(sid, scene_hit=has_scene)
        return out

    # 未触发：消化余波（一轮即清）
    residue = _consume_residue(sid)
    if residue:
        return _build_residue_block(residue)
    return ""
