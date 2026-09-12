"""anon 公共入口——caller 只导这个、不直接 import 子模块。

设计意图（同 tomori）：
  让主流程调用方保持「我只 import anon.api、调几个明确函数」的形态、
  不被爱音专属子系统的内部重构波及。

当前状态：
  · render_supplemental_blocks 已接通 turn_logic（美妆 / 穿搭 / 社交平台 / 留学防御）；
  · post_reply_voice_check 仍是 stub（voice_check 子系统未接线，永远 skipped）。
"""
from __future__ import annotations

from typing import Any
from datetime import datetime

from .canon import get_canon_facts, get_canon_profile
from .voice import VOICE_MANIFEST
from ...registry import canonicalize_name

CHARACTER_NAME = "爱音"


def is_anon(character: str) -> bool:
    """判断 character 是不是爱音。

    名字表只在 `idiolect/registry.py` 维护一份，这里问它——避免「registry 认得、
    角色包不认得」的静默失效（别名解析成功却在包内被拒，注入为空且无报错）。
    """
    return canonicalize_name(character) == "爱音"


def render_supplemental_blocks(
    *,
    character: str,
    now: datetime | None = None,
    last_user_text: str = "",
    context: dict | None = None,
    session_id: str | None = None,
) -> str:
    """爱音专属补充 block 的统一入口。

    返回字符串 = 拼好的、以 `\\n\\n` 分隔的若干 block；
    无内容时返 ""。caller 把它当作普通 prompt 片段拼到 system prompt 末尾。

    内部已接通 turn_logic.build_anon_special_block（美妆 / 穿搭 / 社交平台 / 留学防御）；
    lng_style.surface 与灯灯 / sumimi / Ave Mujica 子系统仍是 TODO。
    """
    if not is_anon(character):
        return ""
    from .turn_logic import build_anon_special_block
    ctx = context if isinstance(context, dict) else {}
    return build_anon_special_block(
        last_user_text,
        character,
        session_id=session_id or ctx.get("session_id"),
        is_developer=bool(ctx.get("is_developer", False)),
    ) or ""


def get_voice_manifest() -> str:
    return VOICE_MANIFEST


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    return {"text": str(reply_text or ""), "violations": {}, "ok": True, "skipped": not is_anon(character)}


def post_reply_voice_check(
    *,
    character: str,
    reply_text: str,
    history: list | None = None,
) -> dict[str, Any]:
    """爱音回复后的语气后处理校验。

    将来检查项（拟）：
      - 起手式去重（ねぇ / えーー / あ、 / ちょっと / あの / 嗯！等等过频）
      - 拉长音控制（「ねぇーー」「えええ」过载）
      - 颜文字 / 感叹号密度（避免过载假阳光）
      - 留学失败话题防御态正确触发（不直接讲深度伤痕、走转移）
      - 「灯灯」call sign 频率（canon 但不能每条都喊）
      - 「都市丽人完美姐姐」假设阳光稀释 canon → flag

    当前 stub 总返 `{"violations": {}, "ok": True, "skipped": True}`。
    """
    if not is_anon(character):
        return {"violations": {}, "ok": True, "skipped": True}
    # TODO[voice_check]: 真正的语气检查
    return {"violations": {}, "ok": True, "skipped": True}
