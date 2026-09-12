"""tomori 公共入口——caller 只导这个、不直接 import 子模块。

设计意图：
  让主流程调用方保持「我只 import tomori.api、调几个明确函数」的形态、
  不被灯专属子系统的内部重构波及。

当前状态：
  · render_supplemental_blocks 已接通 turn_logic（歌词 / 海洋生物 / 昆虫 / 天文 / 石头
    / 凌晨窗口，2026-05-20 起）；
  · post_reply_voice_check 已接线 voice_check 清洗链（2026-09-12 起，
    `TOMORI_VOICE_CHECK_ENABLED=0` 可整体回退为透传）。
"""
from __future__ import annotations

import logging
import os
from typing import Any
from datetime import datetime

from .canon import get_canon_facts, get_canon_profile
from .voice import VOICE_MANIFEST
from ...registry import canonicalize_name
from ...scene_engine import env_enabled

_log = logging.getLogger(__name__)

CHARACTER_NAME = "灯"


def is_tomori(character: str) -> bool:
    """判断 character 是不是灯。

    名字表只在 `idiolect/registry.py` 维护一份，这里问它——本模块原先自带一张
    手写表，比 registry 少 `ともり`，于是那个别名会静默返回空。
    """
    return canonicalize_name(character) == "灯"


def render_supplemental_blocks(
    *,
    character: str,
    now: datetime | None = None,
    last_user_text: str = "",
    context: dict | None = None,
) -> str:
    """灯专属补充 block 的统一入口。

    返回字符串 = 拼好的、以 `\\n\\n` 分隔的若干 block；
    无内容时返 ""。caller 把它当作普通 prompt 片段拼到 system prompt 末尾。

    内部会按子系统组合：
      - 歌词 / 海洋生物 / 昆虫 / 天文 / 石头（text-driven）
      - 凌晨窗口 late_night_window（time-driven、不依赖 user_text）
      - TODO: notebook / lyrics_flow / collection（未实现）

    2026-05-20: 接通 turn_logic.build_turn_special_block、不再是 stub。
    P1 主要为 late_night_window auto_greet 路径打通。
    """
    if not is_tomori(character):
        return ""

    # ─── turn_logic subsystem aggregator ───
    try:
        from .turn_logic import build_turn_special_block
        ctx = context if isinstance(context, dict) else {}
        sid = str(ctx.get("session_id", "") or "") or None
        is_dev = bool(ctx.get("is_developer", False))
        ledger = ctx.get("ledger") if isinstance(ctx.get("ledger"), dict) else None
        mode = str(ctx.get("mode", "chat") or "chat")
        return build_turn_special_block(
            last_user_text or "",
            character,
            session_id=sid,
            is_developer=is_dev,
            now_jst=now,
            ledger=ledger,
            mode=mode,
        )
    except Exception as _err:
        _log.warning("[tomori.api.render_supplemental_blocks] error: %s", _err)
        return ""


def get_voice_manifest() -> str:
    return VOICE_MANIFEST


def post_reply_voice_check(
    *,
    character: str,
    reply_text: str,
    history: list | None = None,
) -> dict[str, Any]:
    """灯回复后的语气清洗 + 起手式去重（2026-09-12 接线）。

    流程：
      1. `voice_check.throttle_opening`（仅当 history 里有 assistant 回复时）：
         起手式跨轮去重轮换 + 连续省略号起手修复。
      2. `voice_check.clean_reply`：呀/啊 清洗 → CJK 空格停顿补偿 → 标点软化 →
         省略号配对 / 归一 / 配额 → 纯省略号气泡扩展。
         随机步骤按输入定种（`idiolect/_text_rng.py`），同一输入两次清洗同输出。

    `TOMORI_VOICE_CHECK_ENABLED=0`（或 off/no/false）整体回退为透传。

    将来检查项（拟，未实现）：
      - sajiao_tail: 句末出现禁词（呢/啦/呀/嘛）
      - confident_modifier: 评价副词（挺/特别/非常/确实/明显/超）
      - high_gravity_dilution: 「一辈子」「我们的歌」「让我们一起迷失」非深度场合误用
      - knowing_summary: 「她是…的人」式人物画像归纳
    """
    if not is_tomori(character):
        return {"violations": {}, "ok": True, "skipped": True}
    if not env_enabled(os.environ.get("TOMORI_VOICE_CHECK_ENABLED")):
        return {"text": str(reply_text or ""), "violations": {}, "ok": True, "skipped": "disabled"}
    try:
        from .voice_check import clean_reply, throttle_opening
        from ..._text_rng import seeded_rng

        text = str(reply_text or "")
        changed: list[str] = []
        prior = [str(m.get("content", "") or "") for m in (history or [])
                 if isinstance(m, dict) and m.get("role") == "assistant"]
        if prior:
            text, tinfo = throttle_opening(text, prior)
            if tinfo.get("replaced") or tinfo.get("stripped") or tinfo.get("double_ellipsis_fixed"):
                changed.append("opening_throttle")

        text, info = clean_reply(text, rng=seeded_rng(text))
        violations = info.get("violations", {})
        changed.extend(k for k in violations if k not in changed)
        return {"text": text, "violations": violations, "changed": changed,
                "ok": bool(info.get("ok", True))}
    except Exception as _err:
        _log.warning("[TomoriVoiceCheck] error: %s", _err)
        return {"text": str(reply_text or ""), "violations": {}, "ok": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text, history=history))
    result.setdefault("text", str(reply_text or ""))
    return result
