"""taki 公共入口——caller 只导这个、不直接 import 子模块。

设计意图：
  让主流程调用方保持「我只 import taki.api、调几个明确函数」的形态、
  不被立希专属子系统的内部重构波及。

当前 stub 状态：
  函数签名先固定下来、内部 return 空字符串 / pass-through、
  让骨架可以被主流程接进去而不影响行为。等子系统真做完再换实现。
"""
from __future__ import annotations

from typing import Any
from datetime import datetime

from .canon import get_canon_facts, get_canon_profile
from .voice import VOICE_MANIFEST

CHARACTER_NAME = "立希"


def is_taki(character: str) -> bool:
    """判断 character 是不是立希。

    用 helper 而不是各处 `character == "立希"` 字面比较、避免名字写法漂移
    （椎名立希 / 立希 / Rikki / Taki 等）。
    """
    if not character:
        return False
    name = str(character).strip().lower()
    return name in ("立希", "taki", "rikki", "椎名立希", "shiina taki")


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

    内部会按子系统组合：
      - drum_dtm.render（如果当下场景能引用到鼓套件 / DTM 工作流）
      - afterglow_fan.surface（蘭 / 巴 出现时的狂热粉行为）
      - family_school_anchor.inject（涉及姐姐 / 真希 / 花咲川转校 canon 时的硬约束）
      - nickname_lock.guide（称呼规则——灯只用本名、其他人正常）

    现在是 stub、永远返 ""——等子系统实现后逐个开。
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
        print(f"[taki.api.render_supplemental_blocks] error: {_err}", flush=True)
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
    """立希回复后的语气后处理校验（不修改 reply、只产出诊断）。

    当前 stub 总返 `{"violations": [], "ok": True}`、子系统实现前没人会跑入分支。

    将来检查项（拟）：
      - visual_claim_detect: 检测对用户的 visual claim（"你穿"/"你长得"等）
      - soft_tone_overuse: 温柔正面词跨轮统计（"好开心""真的很""特别"）
      - sajiao_tail_residue: 句末撒娇词残留（呢/哦/啦/嘛/呀）
      - long_essay_drift: 超过 SSOT 字数上限（普通 5-18 / 技术 ≤30 / 深度 ≤50）
      - nickname_lock_break: 灯被加了任何前缀 / 后缀
      - afterglow_instrument_swap: 蘭 ↔ 巴 乐器混淆
      - know_summary: 「她是…的人」式归纳（立希不做人物画像）
    """
    if not is_taki(character):
        return {"violations": [], "ok": True, "skipped": True}
    # TODO[voice_check]: 真正的语气检查、参考 tomori/voice_check 5-stage chain
    return {"violations": [], "ok": True, "skipped": True}


def postprocess_reply(*, character: str, reply_text: str, history: list | None = None) -> dict[str, Any]:
    result = dict(post_reply_voice_check(character=character, reply_text=reply_text))
    result.setdefault("text", str(reply_text or ""))
    return result
