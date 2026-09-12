"""素世本轮特殊逻辑入口（仿 tomori / taki / anon turn_logic）。

设计意图：
  · canon 给素世的核心特质是「观察先于表达」「轻薄精确的点破」「不替对方命名感受」
  · 这些行为**不是均匀分布在所有对话里**，而是集中在几个可判定的场景：
    观察/点破、红茶/待客、旧事触发
  · 本模块的作用是**在正确场景给出正确的分寸**，而不是让她整体变话多

窄入口：只暴露 `build_soyo_special_block(user_text, character, *, session_id, ...)`。
可关闭：`SOYO_TURN_LOGIC_ENABLED=0`（场景级另有 `SOYO_TURN_LOGIC_<SCENE>_ENABLED`）。

当前子系统（2026-09-12）：
  · `scenes.py`：观察/点破、红茶/待客、旧事触发（场景层：给分寸）
  · `home.py`：家 / 妈妈 / 家务（深模块：主题知识，3 层渐进 + per-session 去重）
  · `wind_ensemble.py`：吹奏乐社 / 低音大提琴（深模块，含「为什么换成贝斯」override）
  · 通用场景层：13 个五角色共有场景里的 `affection` / `play_along`

**轮次预算**：深模块 ≤1 块 + 场景层 ≤1 块 + 通用场景层 ≤1 块 = 最多 3 块。
深模块（主题知识）排在场景层（分寸）前面；没有深模块命中时，
本函数的输出与只有场景层时**逐字节相同**（保证无关场景零漂移）。

触发词纪律（2026-09-11 语料实证）：
  · 采用：CRYCHIC 22 / 睦 47 / 记得 8 / 春日影 8 / 以前 5 / 过去 4 / 咖啡 14 / 茶 9
  · **不采用**「大吉岭」「祥子」「奶茶」——素世语料里不存在
  · **不采用**「为什么」「不是」当点破触发词——出现率过高（31 / 50 次），会大面积误触发；
    改用「对方言行对不上」的**句式模式**（见 scenes.py）

注：本模块产物供 `soyo.api.render_supplemental_blocks` 调用、最终注入 system prompt。
"""
from __future__ import annotations

import os
from typing import Callable

from idiolect.registry import canonicalize_name
from idiolect.scene_engine import NO_LITERAL_COPY, SceneModule, build_scene_blocks

from .home import build_home_special_block
from .scenes import SOYO_SCENES
from .wind_ensemble import build_wind_ensemble_special_block


# ── 深模块层（主题知识 + 分寸）────────────────────────────────────────
# 顺序 = 命中优先级（一轮最多取 1 块）。窄话题在前：乐器/社团比「家里」更具体。
_DEEP_MODULES: tuple[tuple[str, Callable[..., str]], ...] = (
    ("wind_ensemble", build_wind_ensemble_special_block),
    ("home", build_home_special_block),
)
_DEEP_MAX_BLOCKS = 1
# 深模块与场景层话题重叠时，压制场景层对应块（避免同一话题两块正文）
_DEEP_SCENE_OVERLAP: dict[str, tuple[str, ...]] = {}


def _enabled() -> bool:
    raw = os.environ.get("SOYO_TURN_LOGIC_ENABLED")
    if raw is None:
        return True
    return str(raw).strip() not in ("0", "false", "False", "off", "no", "")


def _build_deep_blocks(
    user_text: str, *, session_id: str | None, is_developer: bool
) -> tuple[list[str], list[str]]:
    """深模块层。返回 (blocks, 命中的模块 key)；单个模块异常不影响其它层。"""
    out: list[str] = []
    fired: list[str] = []
    for key, builder in _DEEP_MODULES:
        if len(out) >= _DEEP_MAX_BLOCKS:
            break
        try:
            blk = builder(user_text, session_id=session_id, is_developer=is_developer)
        except Exception as _err:  # pragma: no cover - 防御性
            print(f"[SoyoTurnLogic/{key}] error: {_err}", flush=True)
            continue
        if blk:
            # 统一追加反照抄脚注：深模块的正例是语义锚、不是台词库。
            # 依据见 `character_scene_turn_logic.NO_LITERAL_COPY` 的注释（真实探针证据）。
            out.append(f"{blk.rstrip()}\n{NO_LITERAL_COPY}")
            fired.append(key)
    return out, fired


def _scenes_for(fired: list[str]) -> list[SceneModule]:
    covered = {s for k in fired for s in _DEEP_SCENE_OVERLAP.get(k, ())}
    if not covered:
        return SOYO_SCENES
    return [m for m in SOYO_SCENES if m.key not in covered]


_BLOCK_BORDER = "═" * 72


def _wrap_blocks(blocks: list[str]) -> str:
    if not blocks:
        return ""
    wrapped = [f"{_BLOCK_BORDER}\n{b.rstrip()}\n{_BLOCK_BORDER}" for b in blocks if b]
    return "\n\n".join(wrapped)


def build_soyo_special_block(
    user_text: str,
    character: str,
    *,
    session_id: str | None = None,
    is_developer: bool = False,
    **kwargs: object,
) -> str:
    """素世本轮特殊指引拼装。

    Args:
        user_text:    当前 turn 的 user message
        character:    角色名（素世 / 爽世 / soyo / 長崎そよ 等）
        session_id:   ws session id；用作 per-session 去重 key
        is_developer: True = 本轮对象是开发者，不触发场景/深模块
        **kwargs:     兼容 now_jst / ledger / mode（本模块不用）

    Returns:
        prompt 片段字符串；无内容时返 ""
    """
    # 名字表只有 registry 一份（见 AGENTS.md）：自带名单会与之漂移，
    # 代价是别名能解析到包、却在包内被判 False 静默返空。
    if canonicalize_name(character) != "素世":
        return ""
    if is_developer or not _enabled():
        return ""
    if not user_text:
        return ""
    deep_blocks, fired = _build_deep_blocks(
        user_text, session_id=session_id, is_developer=is_developer)
    blocks = list(deep_blocks)
    blocks.extend(build_scene_blocks(
        user_text, _scenes_for(fired), session_id=session_id, max_blocks=1))
    # 通用场景层（13 个五角色共有的场景）：2026-09-12 新增 `affection`——
    # 素世的挡法是礼貌反问、把球踢回去，不正面接也不慌。
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            "素世", user_text, session_id=session_id, max_blocks=1,
            is_developer=is_developer))
    except Exception as _err:
        print(f"[SoyoTurnLogic/general_scenes] error: {_err}", flush=True)
    return _wrap_blocks(blocks)


build_turn_special_block = build_soyo_special_block
