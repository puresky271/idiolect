"""tomori.turn_logic — 灯本轮对话特殊逻辑入口。

设计意图：
  灯的歌词逻辑不该耦合在 system prompt 构建路径里，集中在这里：

  - **本轮触发**：每次 chat reply 前根据 user_text 判断是否注入特殊指引
  - **窄入口**：只暴露 build_turn_special_block(user_text, character)
  - **可叠加**：内部按场景路由（lyrics / 笔记本 / 收集物 / 等等）、
              caller 不需要知道具体分支
  - **可关闭**：env flag `TOMORI_TURN_LOGIC_ENABLED=0` 一键回退

当前状态：
  · 空 stub、永远返 ""、不破坏现有 prompt 输出
  · 后续按子系统（笔记本 / 歌词流 / 收集癖 / 等）逐个实现

注：本模块产物注入在 prompt 的 `lyrics_context` slot
（保留这个 key 名向后兼容、内部已不止"歌词"用途）。
"""
from __future__ import annotations

import os


def _enabled() -> bool:
    return os.environ.get("TOMORI_TURN_LOGIC_ENABLED", "1").strip() not in ("0", "false", "False", "")


def build_turn_special_block(
    user_text: str,
    character: str,
    *,
    session_id: str | None = None,
    is_developer: bool = False,
    now_jst=None,
    ledger: dict | None = None,
    mode: str = "chat",
) -> str:
    """灯本轮特殊指引拼装。

    Args:
        user_text:    当前 turn 的 user message（chat mode 下不能为空、autogreet 可为空）
        character:    角色名
        session_id:   ws session id（可选）— 子系统用作 per-session 去重 key；
                      None → 子系统 fallback 单一 bucket（共享去重状态）
        is_developer: True = 触发对象是开发者
        now_jst:      当前 JST datetime（time-driven 子系统用、如 late_night_window）
        ledger:       调用方传入的世界状态 dict，读 ledger["plans"][角色]["night_owl_today"]
                      （本仓库不带世界模拟；缺省 None 时按 False 处理）
        mode:         "chat" = 被对方找 / "autogreet" / "idle" = 主动开口

    Returns:
        prompt 片段字符串、无内容时返 ""

    子系统按场景注入：
      - text-driven（依赖 user_text）：歌词 / 海洋生物 / 昆虫 / 天文 / 石头
      - time-driven（不依赖 user_text）：late_night_window（凌晨 + night_owl_today）

    2026-05-20: 加 now_jst/ledger/mode 参数支持 time-driven 子系统、autogreet 可触发。
    """
    if not _enabled() or character != "灯":
        return ""

    # autogreet / idle mode 下 user_text 为空、不能直接 return——time-driven 子系统仍要 fire
    _is_text_driven_only_path = mode == "chat" and not user_text

    blocks: list[str] = []

    if not _is_text_driven_only_path:
        # ─── 子系统 1: 歌词 / 写诗（text-driven） ───
        if user_text:
            try:
                from .lyrics import build_lyrics_special_block
                _lyrics_blk = build_lyrics_special_block(user_text)
                if _lyrics_blk:
                    blocks.append(_lyrics_blk)
            except Exception as _err:
                print(f"[TomoriTurnLogic/lyrics] error: {_err}", flush=True)

        # ─── 子系统 2: 海洋生物 / 水族馆 venue（text-driven） ───
        if user_text:
            try:
                from .marine_life import build_marine_special_block
                _marine_blk = build_marine_special_block(user_text, session_id=session_id, is_developer=is_developer)
                if _marine_blk:
                    blocks.append(_marine_blk)
            except Exception as _err:
                print(f"[TomoriTurnLogic/marine_life] error: {_err}", flush=True)

        # ─── 子系统 3: 昆虫（text-driven） ───
        if user_text:
            try:
                from .insects import build_insect_special_block
                _insect_blk = build_insect_special_block(user_text, session_id=session_id, is_developer=is_developer)
                if _insect_blk:
                    blocks.append(_insect_blk)
            except Exception as _err:
                print(f"[TomoriTurnLogic/insects] error: {_err}", flush=True)

        # ─── 子系统 4: 天文（text-driven） ───
        if user_text:
            try:
                from .astronomy import build_astronomy_special_block
                _astro_blk = build_astronomy_special_block(user_text, session_id=session_id, is_developer=is_developer)
                if _astro_blk:
                    blocks.append(_astro_blk)
            except Exception as _err:
                print(f"[TomoriTurnLogic/astronomy] error: {_err}", flush=True)

        # ─── 子系统 5: 石头（text-driven） ───
        if user_text:
            try:
                from .stones import build_stone_special_block
                _stone_blk = build_stone_special_block(user_text, session_id=session_id, is_developer=is_developer)
                if _stone_blk:
                    blocks.append(_stone_blk)
            except Exception as _err:
                print(f"[TomoriTurnLogic/stones] error: {_err}", flush=True)

    # ─── 子系统 6: 凌晨窗口（time-driven、不依赖 user_text）───
    # autogreet 路径下 user_text 为空也要 fire；topic 模式 user_text 命中关键词也要 fire
    try:
        from .late_night_window import build_late_night_window_special_block
        _late_blk = build_late_night_window_special_block(
            user_text,
            now_jst=now_jst,
            ledger=ledger,
            session_id=session_id,
            is_developer=is_developer,
            mode=mode,
        )
        if _late_blk:
            blocks.append(_late_blk)
    except Exception as _err:
        print(f"[TomoriTurnLogic/late_night_window] error: {_err}", flush=True)

    # ─── 通用场景层（13 个五角色共有的场景） ───
    # 2026-09-12：`affection`（被示好）实测最差——灯中位 50 字 vs 该场景参照中位 10＝过度铺陈。
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            "灯", user_text, session_id=session_id, max_blocks=1,
            is_developer=is_developer))
    except Exception as _err:
        print(f"[TomoriTurnLogic/general_scenes] error: {_err}", flush=True)

    # TODO 后续子系统：情感语无伦次 / NPC 关系敏感度 / 树叶 / 天气

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
