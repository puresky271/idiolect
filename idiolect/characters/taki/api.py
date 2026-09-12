"""taki 公共入口——caller 只导这个、不直接 import 子模块。

设计意图：
  让主流程调用方保持「我只 import taki.api、调几个明确函数」的形态、
  不被立希专属子系统的内部重构波及。

当前状态：
  · render_supplemental_blocks 已接通 turn_logic（作曲 / 熊猫 / 凌晨窗口 / 灯话题 /
    打工 / Afterglow）；
  · post_reply_voice_check 已接线 voice_check 清洗链（2026-09-12 起，
    `TAKI_VOICE_CHECK_ENABLED=0` 可整体回退为透传）。
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

CHARACTER_NAME = "立希"


def is_taki(character: str) -> bool:
    """判断 character 是不是立希。

    名字表只在 `idiolect/registry.py` 维护一份，这里问它——本模块原先自带一张
    手写表（少了 `りき` / `りっきー`），与 registry 不一致会造成静默失效。
    """
    return canonicalize_name(character) == "立希"


def render_supplemental_blocks(
    *,
    character: str,
    now: datetime | None = None,
    last_user_text: str = "",
    context: dict | None = None,
) -> str:
    """立希专属补充 block 的统一入口。

    返回字符串 = 拼好的、以 `\\n\\n` 分隔的若干 block；
    无内容时返 ""。caller 把它当作普通 prompt 片段拼到 system prompt 末尾。

    内部已接通 turn_logic.build_taki_special_block（作曲 / 熊猫 / 凌晨窗口 /
    灯话题 / 打工 / Afterglow 狂热粉）；drum_dtm / family_school_anchor /
    nickname_lock 仍是 TODO。
    """
    if not is_taki(character):
        return ""

    # ─── turn_logic subsystem aggregator ───
    try:
        from .turn_logic import build_taki_special_block
        ctx = context if isinstance(context, dict) else {}
        sid = str(ctx.get("session_id", "") or "") or None
        is_dev = bool(ctx.get("is_developer", False))
        ledger = ctx.get("ledger") if isinstance(ctx.get("ledger"), dict) else None
        mode = str(ctx.get("mode", "chat") or "chat")
        # 2026-05-12: scene_mode_adapter 用的多路加权信号、由 caller 预 compute
        # 字段（任一存在即可激活 adapter）：
        #   user_emotion / relation_tier / deep_moment / history
        scene_context: dict = {}
        for key in ("user_emotion", "relation_tier", "deep_moment", "history"):
            if key in ctx:
                scene_context[key] = ctx[key]
        return build_taki_special_block(
            last_user_text or "",
            character,
            session_id=sid,
            is_developer=is_dev,
            now_jst=now,
            ledger=ledger,
            mode=mode,
            scene_context=(scene_context or None),
        )
    except Exception as _err:
        _log.warning("[taki.api.render_supplemental_blocks] error: %s", _err)
        return ""


def get_voice_manifest() -> str:
    return VOICE_MANIFEST

    # TODO[afterglow_fan]: 蘭/巴 出现时切狂热粉行为（害羞 / 紧张 / 踢翻凳子）
    # TODO[family_school_anchor]: 姐姐 / 真希 / 祥子 / 花咲川转校 canon 触发硬约束
    # TODO[nickname_lock]: 称呼系统注入（灯 = 本名零修饰、其他人正常名字）
    # TODO[topic_tomori_soften]: 聊到灯相关话题时语气放软


def post_reply_voice_check(
    *,
    character: str,
    reply_text: str,
) -> dict[str, Any]:
    """立希回复后的语气清洗（2026-09-12 接线）。

    跑 `taki.voice_check.clean_reply`——原则**只删不换**：
      · 句首软回应起手（嗯嗯/好的呀/诶嘿/呐呐 等，先吃长 phrase）
      · 句末撒娇词（呢/哦/啦/嘛/呀，词内合法位置有 lookbehind 保护）
      · 装饰符号（♪~———）/ 颜文字 / 多重感叹问号减到 1

    `TAKI_VOICE_CHECK_ENABLED=0`（或 off/no/false）整体回退为透传。

    将来检查项（拟，未实现）：
      - visual_claim_detect: 检测对用户的 visual claim（"你穿"/"你长得"等）
      - soft_tone_overuse: 温柔正面词跨轮统计（"好开心""真的很""特别"）
      - long_essay_drift: 超过 SSOT 字数上限（普通 5-18 / 技术 ≤30 / 深度 ≤50）
      - nickname_lock_break: 灯被加了任何前缀 / 后缀
      - afterglow_instrument_swap: 蘭 ↔ 巴 乐器混淆
      - know_summary: 「她是…的人」式归纳（立希不做人物画像）
    """
    if not is_taki(character):
        return {"violations": {}, "ok": True, "skipped": True}
    if not env_enabled(os.environ.get("TAKI_VOICE_CHECK_ENABLED")):
        return {"text": str(reply_text or ""), "violations": {}, "ok": True, "skipped": "disabled"}
    try:
        from .voice_check import clean_reply
        text, info = clean_reply(str(reply_text or ""))
        violations = info.get("violations", {})
        return {"text": text, "violations": violations, "changed": list(violations),
                "ok": bool(info.get("ok", True))}
    except Exception as _err:
        _log.warning("[TakiVoiceCheck] error: %s", _err)
        return {"text": str(reply_text or ""), "violations": {}, "ok": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text))
    result.setdefault("text", str(reply_text or ""))
    return result
