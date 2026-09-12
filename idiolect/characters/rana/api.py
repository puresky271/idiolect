"""乐奈角色包公共入口。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .canon import CHARACTER_NAME, get_canon_facts, get_canon_profile
from .voice import get_voice_manifest


def is_rana(character: str) -> bool:
    return str(character or "").strip().lower() in {
        "乐奈", "楽奈", "rana", "要楽奈", "kaname rana",
    }


def render_supplemental_blocks(*, character: str, last_user_text: str = "", context: dict | None = None, now: datetime | None = None, session_id: str | None = None) -> str:
    if not is_rana(character):
        return ""
    from .turn_logic import build_rana_special_block
    ctx = context if isinstance(context, dict) else {}
    return build_rana_special_block(
        last_user_text,
        character,
        session_id=session_id or str(ctx.get("session_id", "") or "") or None,
        is_developer=bool(ctx.get("is_developer", False)),
        now_jst=now,
        ledger=ctx.get("ledger"),
        mode=str(ctx.get("mode", "chat") or "chat"),
    )


def post_reply_voice_check(*, character: str, reply_text: str) -> dict[str, Any]:
    """乐奈回复后的语气清洗 + 风格改写 + 诊断。

    1. `rana.voice_check.clean_reply` —— **无损**清洗：超配额感叹号降级（语料出现率仅 3%）、
       连排句号归一、省略号归一。
    2. `rana.voice_check.strip_redundant_ack` —— **风格改写**（会删字，因此不放进 `clean_reply`）：
       内容已经够长时去掉冗余的「嗯。」起手。依据：原作起手 55% 是名词直出、语气词只有 8%，
       而生产臂是 19% / 67%（旧批次记录；当前 repo_standalone 批次实测 24% / 57%，
       复现见 `tools/score/_noun_initial.py`）；prompt 侧两次 A/B 均无显著效果，所以改用后处理。
       短确认（「嗯。开心」）与疑问起手（「嗯？」）都不动；`RANA_VOICE_CHECK_ACK_STRIP=0` 可关。
    3. 诊断：助手腔/越界（关系承诺 / 元叙述 / 心理归因 / 工整收束 / 客服腔 / 视觉声称）
       + 长度与标点阈值（中位 6 字、p90 12 字、硬上限 16）
    """
    if not is_rana(character):
        return {"text": str(reply_text or ""), "violations": {}, "ok": True, "skipped": True}
    try:
        from .voice_check import clean_reply, strip_redundant_ack

        text, info = clean_reply(reply_text)
        changed = list(info.get("changed", []))
        text, ack_done = strip_redundant_ack(text)
        if ack_done:
            changed.append("ack_stripped")
        return {"text": text, "violations": info.get("violations", {}),
                "changed": changed, "ok": bool(info.get("ok", True))}
    except Exception as _err:  # noqa: BLE001
        print(f"[RanaVoiceCheck] error: {_err}", flush=True)
        return {"text": str(reply_text or ""), "violations": {}, "ok": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text))
    result.setdefault("text", str(reply_text or ""))
    return result
