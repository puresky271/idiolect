"""素世角色包公共入口。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .canon import CHARACTER_NAME, get_canon_facts, get_canon_profile
from .voice import get_voice_manifest
from ...registry import canonicalize_name

_log = logging.getLogger(__name__)


def is_soyo(character: str) -> bool:
    """判断 character 是不是素世。名字表只在 `idiolect/registry.py` 维护一份。"""
    return canonicalize_name(character) == "素世"


def render_supplemental_blocks(*, character: str, last_user_text: str = "", context: dict | None = None, now: datetime | None = None, session_id: str | None = None) -> str:
    if not is_soyo(character):
        return ""
    from .turn_logic import build_soyo_special_block
    ctx = context if isinstance(context, dict) else {}
    return build_soyo_special_block(
        last_user_text,
        character,
        session_id=session_id or str(ctx.get("session_id", "") or "") or None,
        is_developer=bool(ctx.get("is_developer", False)),
        now_jst=now,
        ledger=ctx.get("ledger"),
        mode=str(ctx.get("mode", "chat") or "chat"),
    )


def post_reply_voice_check(*, character: str, reply_text: str) -> dict[str, Any]:
    """素世回复后的语气清洗 + 诊断（不改语义，只做无损替换）。

    跑 `soyo.voice_check.clean_reply`：
      · 无损清洗：超配额感叹号降级、连排句号归一、省略号归一
      · 诊断：助手腔/越界（关系承诺 / 元叙述 / 心理归因 / 命名感受 / 工整收束 / 客服腔）
        + 素世专属（裸本名 ≥2 次）、长度与标点阈值
    """
    if not is_soyo(character):
        return {"text": str(reply_text or ""), "violations": {}, "ok": True, "skipped": True}
    try:
        from .voice_check import clean_reply

        text, info = clean_reply(reply_text)
        return {"text": text, "violations": info.get("violations", {}),
                "changed": info.get("changed", []), "ok": bool(info.get("ok", True))}
    except Exception as _err:  # noqa: BLE001
        _log.warning("[SoyoVoiceCheck] error: %s", _err)
        return {"text": str(reply_text or ""), "violations": {}, "ok": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text))
    result.setdefault("text", str(reply_text or ""))
    return result
