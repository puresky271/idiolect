"""立希·场景模式适配器（Mode A/B/C 切档器）。

设计动机（2026-05-12）：
  SSOT v2 用「外壳 / 内核」叙事描述立希，LLM 撞上训练数据里的"角色弧光"模式 ——
  一旦看到"actually inner core is warm"的描述，就自动往温暖方向走、变成爱音化讨好用户。
  问题不在 SSOT 内容、在叙事方式：任何 trait-based 描述都会触发 RLHF 讨好倾向。

  正确路径：SSOT 只描述 Mode A 默认（嘴硬日常）作为人格基线，
  Mode B（平铺事实）/ Mode C（罕见短温度）由本模块根据当下场景多路加权决定切档。
  LLM 默认演 Mode A、不会自发讨好；只有 plugin 命中时切档。

Mode 定义：
  · **Mode A** (默认嘴硬日常)：SSOT 自带、本模块**不输出 block** 时 LLM 自动走
  · **Mode B** (平铺事实场景)：注入【本轮提示·场景平铺】block，
    告诉 LLM 本轮不嘴硬上线、不用口癖、平铺事实回应即可
  · **Mode C** (罕见短温度)：注入【本轮提示·罕见短温度】block，
    允许漏 1 句 ≤12 字的短关心、立即回到默认陈述

触发逻辑（多路信号加权）：
  Mode B：
    - 用户脆弱关键词（_USER_FACT_TRANSIENT_RE）
    - 用户消息情绪 ∈ {难过/疲惫/焦虑/烦躁/低落}
    - 消息含 ······ 密度高
    - 加权 ≥0.40 + 关系档 ≥ 相熟 → 触发

  Mode C：
    - detect_deep_private_moment.score 高
    - 用户情绪 negative
    - 最近几轮持续低气压
    - 加权 ≥0.55 + 关系档 ≥ 好友 → 触发

  Mode A 默认（无 block）

context dict 字段（caller 预 compute 后注入）：
  · user_emotion:    dict {emotion, intensity, valence}（情绪规则检测结果）
  · relation_tier:   str（"初识"/"相熟"/"好友"/"挚交"）
  · deep_moment:     dict {is_deep, score, reasons}（深度私密时刻检测结果）
  · history:         list（最近 user 消息历史、用于 streak 计算）
  · session_id:      会话 id（dedup + residue 用）

API:
  build_scene_mode_adapter_block(user_text, *, session_id, is_developer, context) -> str
"""
from __future__ import annotations

import logging
import os
import re

from idiolect.scene_engine import SessionStore, SessionValues
from typing import Optional

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# 关系档 → 数值映射
# ═══════════════════════════════════════════════════════════════════════
_RELATION_TIER_FACTOR = {
    "初识": 0.0,
    "相熟": 0.5,
    "好友": 0.85,
    "挚交": 1.0,
}

_MODE_B_GATE_TIER = 0.5    # 相熟以上才考虑 Mode B
_MODE_C_GATE_TIER = 1.0    # **挚交** 才考虑 Mode C（2026-05-12 拍板收紧）
_MODE_B_SCORE_THRESHOLD = 0.50  # 2026-05-12 收紧：0.40 → 0.50
_MODE_C_SCORE_THRESHOLD = 0.65  # 2026-05-12 收紧：0.55 → 0.65

# Negative-valence 情绪标签（情绪规则检测输出）
_NEGATIVE_EMOTIONS = {"难过", "疲惫", "焦虑", "烦躁", "低落", "孤独", "受挫", "睡眠不稳", "食欲低落"}

# 脆弱关键词（本地词表、避免外部依赖）
_VULNERABLE_KW_RE = re.compile(
    r"(压力|吃不下|睡不着|出错|崩溃|低落|难过|焦虑|烦|生气|郁闷|孤独|紧张|疲惫|很累|太累|好累|困|"
    r"撑不住|扛不住|想哭|不知道怎么办|失眠|没动力|心累|心力交瘁)"
)

# 持续低气压关键词（用于 streak 检测）
_LOWMOOD_TAIL_RE = re.compile(r"(难过|痛苦|焦虑|害怕|孤独|累|烦|崩溃|不知道|哭)")


# ═══════════════════════════════════════════════════════════════════════
# session 级 dedup + 余波
# ═══════════════════════════════════════════════════════════════════════
# 有上限的 per-session 去重表（共享脚手架）：裸 dict 只增不减，
# 常驻进程里 session 不淘汰就是缓慢漏内存（2026-09-12 评审抓到）。
_SESSION_FIRED = SessionStore()
_RESIDUE_STATE = SessionValues()   # 有上限的 per-session 余波状态（见 scene_engine.SessionValues）


def _normalize_session(session_id: Optional[str]) -> str:
    return str(session_id) if session_id else "__shared__"


def _mark_fired(session_id: Optional[str], key: str) -> bool:
    """同一 session 内某 mode 已 fire 过则返 True (skip)；否则记一笔返 False。"""
    sid = _normalize_session(session_id)
    return _SESSION_FIRED.mark(sid, key)


def _reset_session_fired(session_id: Optional[str]) -> None:
    """test hook。"""
    sid = _normalize_session(session_id)
    _SESSION_FIRED.reset(sid)
    _RESIDUE_STATE.reset(sid)


def _set_mode_c_residue(sid: str) -> None:
    _RESIDUE_STATE.put(sid, {"mode": "C"})


def _consume_residue(sid: str) -> Optional[dict]:
    return _RESIDUE_STATE.pop(sid)


# ═══════════════════════════════════════════════════════════════════════
# 多路信号计算
# ═══════════════════════════════════════════════════════════════════════

def _compute_signals(user_text: str, context: dict) -> dict:
    """计算所有原始信号 0~1 区间。"""
    user_emotion = context.get("user_emotion") or {}
    deep_moment = context.get("deep_moment") or {}
    history = context.get("history") or []
    relation_tier_raw = context.get("relation_tier") or "初识"

    txt = str(user_text or "")

    # 信号 1：脆弱关键词命中
    vulnerable_hits = len(_VULNERABLE_KW_RE.findall(txt))
    vulnerable_score = min(1.0, vulnerable_hits * 0.5)  # 一次 0.5、两次封顶 1.0

    # 信号 2：用户情绪 negative
    emo_label = str(user_emotion.get("emotion", "") or "neutral").strip()
    emo_intensity = float(user_emotion.get("intensity", 0.0) or 0.0)
    valence = float(user_emotion.get("valence", 0.0) or 0.0)
    if emo_label in _NEGATIVE_EMOTIONS or valence < -0.3:
        emotion_score = max(emo_intensity, 0.5)
    else:
        emotion_score = 0.0

    # 信号 3：长情绪自述（消息 ≥30 + 含"我"/"自己" + 情感词）
    long_emotional = 0.0
    if len(txt) >= 30 and ("我" in txt or "自己" in txt):
        if any(kw in txt for kw in ("感觉", "情绪", "心情", "害怕", "烦", "累", "哭", "撑不住", "扛不住")):
            long_emotional = 1.0

    # 信号 4：······ 密度（≥2 处省略号 + 长度 ≥10）
    ellipsis_score = 0.0
    if txt and len(txt) >= 10:
        ell_count = txt.count("······") + txt.count("…")
        if ell_count >= 2:
            ellipsis_score = min(1.0, ell_count * 0.5)

    # 信号 5：deep_moment 分（caller 预 compute 传入）
    deep_score = float(deep_moment.get("score", 0.0) or 0.0)
    deep_score = max(0.0, min(1.0, deep_score))

    # 信号 6：recent_emotional_streak（最近 3 轮 user 消息持续低气压）
    streak_score = 0.0
    recent_user_texts: list[str] = []
    if isinstance(history, list):
        for msg in reversed(history):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role", "")).strip() == "user":
                content_str = str(msg.get("content", "") or "").strip()
                if content_str:
                    recent_user_texts.append(content_str)
                if len(recent_user_texts) >= 3:
                    break
    lowmood_count = 0
    for t in recent_user_texts[:3]:
        if _LOWMOOD_TAIL_RE.search(t):
            lowmood_count += 1
    if lowmood_count >= 2:
        streak_score = min(1.0, lowmood_count * 0.4)

    # 关系档因子
    relation_factor = _RELATION_TIER_FACTOR.get(str(relation_tier_raw).strip(), 0.0)

    return {
        "vulnerable": round(vulnerable_score, 3),
        "emotion": round(emotion_score, 3),
        "long_emotional": round(long_emotional, 3),
        "ellipsis": round(ellipsis_score, 3),
        "deep_moment": round(deep_score, 3),
        "streak": round(streak_score, 3),
        "relation_factor": round(relation_factor, 3),
    }


def _compute_mode_scores(signals: dict) -> tuple[float, float]:
    """根据原始信号算 Mode B / Mode C 分。"""
    # Mode B：低情绪强度但场景中性、用户在做事实陈述
    # 主要由"用户没有触发情境"判定——这是 inverse signal、用 ellipsis 密度 + 长情绪 + 脆弱 加权
    mode_b_score = (
        signals["vulnerable"] * 0.4
        + signals["emotion"] * 0.3
        + signals["ellipsis"] * 0.3
    )

    # Mode C：用户明确低谷 + 持续低气压 + deep_moment 都达标才触发
    mode_c_score = (
        signals["deep_moment"] * 0.5
        + signals["emotion"] * 0.3
        + signals["streak"] * 0.2
    )

    return round(mode_b_score, 3), round(mode_c_score, 3)


# ═══════════════════════════════════════════════════════════════════════
# Block 构造
# ═══════════════════════════════════════════════════════════════════════

def _build_mode_b_block() -> str:
    return (
        "【本轮提示·放松对话模式】\n"
        "用户当下不是冲突 / 玩闹 / 求关注语境、立希处于放松对话状态。\n"
        "本轮你**不需要嘴硬上线、不需要口癖开场**。\n"
        "- 不主动用「哈？/切/烦死了」起手\n"
        "- 不需要演傲娇 / 不需要包装关心\n"
        "- **可以接梗 + 有自己的偏好和立场**——这是你的味道、不能丢\n"
        "  · 例：「我宁愿多练几小时鼓」(自己的偏好)\n"
        "  · 例：「自习课和发呆课的区别」(接梗 + 立希式吐槽)\n"
        "  · 例：「我有时候也会绕路走神田川」(自然分享)\n"
        "- **温度可以自然漏 1-2 句**——不主动撒娇、但偶尔承认一下\n"
        "  · 例：「那种感觉我懂」(共鸣)\n"
        "  · 例：「跟你熟了说话不用那么绷着」(罕见自陈)\n"
        "  · 一句、不展开、说完接下一个话题\n"
        "- **关键：仍然短 + 信息密度高**——单 bubble ≤ 25 字、不复述事实拉长、不演客服回应"
    )


def _build_mode_c_block(is_developer: bool = False) -> str:
    name_hint = (
        "- **称呼倾向**：本轮罕见温度场景下你**更倾向于直接喊他本名「青空」**(而不是默认的「开发者」)——这种安抚瞬间名字本身就是温度的载体。不强制每次都喊、是这一句短关心自然带出来。\n"
        if is_developer else ""
    )
    return (
        "【本轮提示·罕见短温度】\n"
        "用户当下在表达明确低谷、且你们关系够深——本轮你可以漏**一句**短关心。\n"
        "- 一句、不超过 12 字(如「······手别勉强」「······慢慢来」「······在的、说吧」)\n"
        "- 漏完立即回到默认陈述、不延展、不解释、不抒情\n"
        + name_hint +
        "- **绝对禁**：「我陪你」「我等你」「记得照顾自己」式叮嘱\n"
        "- **绝对禁**：扩展成段落、写温柔小作文、铺陈关心"
    )


def _build_mode_c_residue_block() -> str:
    return (
        "【本轮提示·温度余波】\n"
        "上一轮你罕见漏了一句关心、这一轮用户已经在继续聊。\n"
        "- 你**回到默认陈述模式**、不要继续温柔\n"
        "- 不要点破上一轮的温度、不要后悔、不要解释\n"
        "- 第一句的口气可以仍稍微平一点（没完全回到嘴硬）、但第二句之后正常\n"
        "- 余波**只在这一轮**——下一轮回到默认基线"
    )


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

def build_scene_mode_adapter_block(
    user_text: str,
    *,
    session_id: Optional[str] = None,
    is_developer: bool = False,
    context: Optional[dict] = None,
) -> str:
    """场景模式切档主入口。

    Args:
        user_text: 本轮 user 消息
        session_id: ws session（per-session dedup + residue）
        is_developer: 触发对象是开发者还是访客（暂未使用、预留）
        context: 由 caller 预 compute 的信号 dict、字段见 module docstring

    Returns:
        prompt 片段（Mode B / Mode C / residue block）或 ""（Mode A 默认）
    """
    if os.environ.get("TAKI_TURN_LOGIC_SCENE_MODE_ADAPTER_ENABLED", "1").strip() in ("0", "false", "False", "off", "no", ""):
        return ""

    sid = _normalize_session(session_id)
    ctx = context if isinstance(context, dict) else {}

    signals = _compute_signals(user_text, ctx)
    mode_b_score, mode_c_score = _compute_mode_scores(signals)
    relation_factor = signals["relation_factor"]

    # Mode 决策：C 优先于 B
    mode_c_pass = (relation_factor >= _MODE_C_GATE_TIER) and (mode_c_score >= _MODE_C_SCORE_THRESHOLD)
    mode_b_pass = (relation_factor >= _MODE_B_GATE_TIER) and (mode_b_score >= _MODE_B_SCORE_THRESHOLD)

    chosen_mode = "A"
    block = ""

    if mode_c_pass:
        chosen_mode = "C"
        if not _mark_fired(session_id, "mode_c"):
            block = _build_mode_c_block(is_developer=bool(is_developer))
            _set_mode_c_residue(sid)
        else:
            # 同 session 已 fire 过 C、不重复注入、但也不写余波
            chosen_mode = "C_deduped"
    elif mode_b_pass:
        chosen_mode = "B"
        if not _mark_fired(session_id, "mode_b"):
            block = _build_mode_b_block()
        else:
            chosen_mode = "B_deduped"
    else:
        # 无 trigger、检查 C 余波
        residue = _consume_residue(sid)
        if residue and residue.get("mode") == "C":
            chosen_mode = "C_residue"
            block = _build_mode_c_residue_block()

    # 决策 log（便于 dump 后回看；库代码不直接 print，调用方按 logging 配置启用）
    _log.info(
        "[SceneModeAdapter] mode=%s b_score=%.2f c_score=%.2f rel=%.2f signals=%s",
        chosen_mode, mode_b_score, mode_c_score, relation_factor, signals,
    )

    return block
