"""anon.turn_logic — 爱音本轮对话特殊逻辑入口（仿 tomori.turn_logic）。

设计意图：
  通用 prompt 路径不该堆爱音专属热词触发，爱音专属逻辑集中在这里：

  - **本轮触发**：每次 chat reply 前根据 user_text 判断是否注入特殊指引
  - **窄入口**：只暴露 build_anon_special_block(user_text, character, *, session_id)
  - **可叠加**：内部按场景路由（美妆 / 留学防御 / 灯灯 / sumimi / Ave Mujica / etc.）、
              caller 不需要知道具体分支
  - **可关闭**：env flag `ANON_TURN_LOGIC_ENABLED=0` 一键回退

当前状态（2026-05-10）：
  · 子系统 1：美妆 / 化妆品（cosmetics.py）— canon 钩子 = 喵梦/若麦 粉丝兴奋
  · 子系统 2：穿搭 / 服装设计（fashion.py）— canon 钩子 = ANON TOKYO（自创品牌+被否决队名）+ 素世「时尚霸凌」
  · 子系统 3：社交平台 / 网络媒体（social_media.py）— canon 钩子 = MyGO SNS 担当（让初华关注 + 跨乐队对照素世 CRYCHIC）
  · 子系统 4：留学失败防御态（london_defense.py）— **心理 canon 不是知识库**、5 motive posture + 1 轮情绪余波
  · 后续按子系统（灯灯 / sumimi / Ave Mujica）逐个加

注：本模块产物注入到 prompt 补充 slot（供 anon.api
   render_supplemental_blocks 调用）。
"""
from __future__ import annotations

import os


def _enabled() -> bool:
    return os.environ.get("ANON_TURN_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "off", "no", "")


def build_anon_special_block(
    user_text: str,
    character: str,
    *,
    session_id: str | None = None,
    is_developer: bool = False,
) -> str:
    """爱音本轮特殊指引拼装。

    Args:
        user_text:    当前 turn 的 user message
        character:    角色名
        session_id:   ws session id（可选）— 子系统用作 per-session 去重 key；
                      None → 子系统 fallback 单一 bucket（共享去重状态）
        is_developer: True = 本轮触发对象是**开发者**（smoke / debug / config）、
                      False = 本轮触发对象是**普通用户**（in-canon 对话）。
                      子系统按此区分 framing + 行为：
                        - 标签：cognitive layer 显示「开发者」or「普通用户」
                        - london_defense：dev 不写 / 不消化 residue + 底子放轻 + deep 不真正打开

    Returns:
        prompt 片段字符串、无内容时返 ""

    现在子系统：
      · cosmetics       — 美妆 / 化妆品（3 层渐进激活 + 喵梦/若麦 canon override）
      · fashion         — 穿搭 / 服装设计（3 层 + ANON TOKYO + 素世「时尚霸凌」双 canon override）
      · social_media    — 社交平台 / 网络媒体（3 层 + MyGO SNS 担当 canon override）
      · london_defense  — 留学失败防御态（心理 canon、5 motive posture + 1 轮情绪余波）

    后续 TODO：
      · tomori_special — 灯灯粘着特殊柔软
      · sumimi_fan     — sumimi 真奈粉丝兴奋
      · ave_mujica_canon — Ep12 借吉他复合情绪
    """
    # 兼容多种名字写法（爱音 / 愛音 / Anon ...）
    try:
        from ..api import is_anon
        if not is_anon(character):
            return ""
    except Exception:
        if character != "爱音":
            return ""

    if not _enabled():
        return ""
    if not user_text:
        return ""

    blocks: list[str] = []

    # ─── 子系统 1: 美妆 / 化妆品 ───
    try:
        from .cosmetics import build_cosmetics_special_block
        _cos_blk = build_cosmetics_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _cos_blk:
            blocks.append(_cos_blk)
    except Exception as _err:
        print(f"[AnonTurnLogic/cosmetics] error: {_err}", flush=True)

    # ─── 子系统 2: 穿搭 / 服装设计 / ANON TOKYO ───
    try:
        from .fashion import build_fashion_special_block
        _fashion_blk = build_fashion_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _fashion_blk:
            blocks.append(_fashion_blk)
    except Exception as _err:
        print(f"[AnonTurnLogic/fashion] error: {_err}", flush=True)

    # ─── 子系统 3: 社交平台 / 网络媒体 / MyGO SNS 担当 ───
    try:
        from .social_media import build_social_media_special_block
        _social_blk = build_social_media_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _social_blk:
            blocks.append(_social_blk)
    except Exception as _err:
        print(f"[AnonTurnLogic/social_media] error: {_err}", flush=True)

    # ─── 子系统 4: 留学失败防御态（心理 canon、不是知识库） ───
    try:
        from .london_defense import build_london_defense_special_block
        _london_blk = build_london_defense_special_block(user_text, session_id=session_id, is_developer=is_developer)
        if _london_blk:
            blocks.append(_london_blk)
    except Exception as _err:
        print(f"[AnonTurnLogic/london_defense] error: {_err}", flush=True)

    # ─── 通用场景层（13 个五角色共有的场景） ───
    # 2026-09-12：`affection`（被示好）——爱音的处理方式是用聒噪掩盖、但不承诺。
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            "爱音", user_text, session_id=session_id, max_blocks=1,
            is_developer=is_developer))
    except Exception as _err:
        print(f"[AnonTurnLogic/general_scenes] error: {_err}", flush=True)

    # TODO 后续子系统：灯灯 / sumimi / Ave Mujica

    # 双线包装：每个 block 独立加 ═════ 上下边界、让 LLM 视觉上把它们当独立 fence 看待
    return _wrap_blocks(blocks)


# ─────────────────────────────────────────────────────────────
# 双线包装 helper（5 角色 turn_logic 共用形态）
# ─────────────────────────────────────────────────────────────
_BLOCK_BORDER = "═" * 72


def _wrap_blocks(blocks: list[str]) -> str:
    """每个 block 加双线上下边界、之间用空行隔开。"""
    if not blocks:
        return ""
    wrapped = [f"{_BLOCK_BORDER}\n{b.rstrip()}\n{_BLOCK_BORDER}" for b in blocks if b]
    return "\n\n".join(wrapped)
