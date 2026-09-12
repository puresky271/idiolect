"""tomori 公共入口——caller 只导这个、不直接 import 子模块。

设计意图：
  让 mygo / chat_server / pilot_registry 这些主流程文件保持「我只 import tomori.api、
  调几个明确函数」的形态、不被灯专属子系统的内部重构波及。

当前 stub 状态：
  函数签名先固定下来、内部 return 空字符串 / pass-through、
  让骨架可以被主流程接进去而不影响行为。等子系统真做完再换实现。
"""
from __future__ import annotations

from typing import Any
from datetime import datetime

from .canon import get_canon_facts, get_canon_profile
from .voice import VOICE_MANIFEST

CHARACTER_NAME = "灯"


def is_tomori(character: str) -> bool:
    """判断 character 是不是灯。

    用 helper 而不是各处 `character == "灯"` 字面比较、避免名字写法漂移
    （高松灯 / 灯 / Tomori / tomorin 等）。
    """
    if not character:
        return False
    name = str(character).strip().lower()
    return name in ("灯", "tomori", "tomorin", "高松灯", "高松燈", "takamatsu tomori")


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
        print(f"[tomori.api.render_supplemental_blocks] error: {_err}", flush=True)
        return ""


def get_voice_manifest() -> str:
    return VOICE_MANIFEST


def post_reply_voice_check(
    *,
    character: str,
    reply_text: str,
) -> dict[str, Any]:
    """灯回复后的语气后处理校验（不修改 reply、只产出诊断）。

    当前 stub 总返 `{"violations": [], "ok": True}`、子系统实现前没人会跑入分支。

    将来检查项（拟）：
      - ellipsis_overuse: 『…』数量 > 段数、或当分隔符滥用
      - sajiao_tail: 句末出现禁词（呢/啦/哦/呀/嘛）
      - confident_modifier: 评价副词（挺/特别/非常/确实/明显/超）
      - high_gravity_dilution: 「一辈子」「我们的歌」「让我们一起迷失」非深度场合误用
      - knowing_summary: 「她是…的人」式人物画像归纳
    """
    if not is_tomori(character):
        return {"violations": [], "ok": True, "skipped": True}
    # TODO[voice_check]: 真正的语气检查
    return {"violations": [], "ok": True, "skipped": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text))
    result.setdefault("text", str(reply_text or ""))
    return result
