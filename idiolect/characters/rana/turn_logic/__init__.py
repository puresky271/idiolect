"""乐奈本轮特殊逻辑入口。

设计意图（与既有角色区分开）：
  · tomori 的 turn_logic 是**知识扩展**（昆虫 / 天文 / 海洋生物）
  · taki 的主题是**什么时候卸下防御**
  · 素世的主题是**什么时候点破、点到什么程度**
  · 乐奈的主题是**她什么时候话会多一点、那点话怎么说**——
    她默认极简（金标准中位 6 字、≤6 字占 57%），但有几个场景允许结构变松。

窄入口：只暴露 `build_rana_special_block(user_text, character, *, session_id, ...)`。
可关闭：`RANA_TURN_LOGIC_ENABLED=0` 一键回退（场景级另有 `RANA_TURN_LOGIC_<SCENE>_ENABLED`）。

当前子系统（2026-09-12）：
  · `scenes.py`：吉他/演出、抹茶/食物、猫/观察 —— 触发词全部经语料实证
  · `space.py`：外婆 / SPACE / 容身之处（深模块，含「外婆来听演出」override）
  · `nap.py`：困 / 午睡 / 找地方睡（深模块）
  · `interesting.py`：「有趣」标尺（深模块，含「有趣的女人」旧说法 override）
  · `cat_talk.py`：猫 / 能听懂猫说话（深模块）
  · 通用场景层：13 个五角色共有场景里的 `affection` / `play_along`

**轮次预算**：深模块 ≤1 块 + 场景层 ≤1 块 + 通用场景层 ≤1 块 = 最多 3 块。
深模块排在场景层前面；`cat_talk` 命中时压制场景层的 `rana_cat`（同一话题不写两块）。
没有深模块命中时，本函数的输出与只有场景层时**逐字节相同**。

装配样板（深模块执行 / 重叠压制 / 通用场景层 / fence 包装 / env 开关语义）
统一下沉在 `idiolect.scene_engine`，本文件只声明数据与顺序。

注：本模块产物供 `rana.api.render_supplemental_blocks` 调用、最终注入 system prompt。
"""
from __future__ import annotations

import os
from typing import Callable

from idiolect.registry import canonicalize_name
from idiolect.scene_engine import (
    SceneModule,
    append_general_scene_blocks,
    build_scene_blocks,
    env_enabled,
    run_modules,
    uncovered_scenes,
    wrap_blocks,
)

from .cat_talk import build_cat_talk_special_block
from .interesting import build_interesting_special_block
from .nap import build_nap_special_block
from .scenes import RANA_SCENES
from .space import build_space_special_block


# ── 深模块层（主题知识 + 分寸）────────────────────────────────────────
# 顺序 = 命中优先级（一轮最多取 1 块）。`space` 放最前：它的触发词最重（外婆/归宿），
# 且猫/吉他等话题即使被挤掉也还有场景层兜着。
_DEEP_MODULES: tuple[tuple[str, Callable[..., str]], ...] = (
    ("space", build_space_special_block),
    ("nap", build_nap_special_block),
    ("interesting", build_interesting_special_block),
    ("cat_talk", build_cat_talk_special_block),
)
_DEEP_MAX_BLOCKS = 1
# 深模块与场景层话题重叠时，压制场景层对应块（避免同一话题两块正文）
_DEEP_SCENE_OVERLAP: dict[str, tuple[str, ...]] = {
    "cat_talk": ("rana_cat",),
}


def _enabled() -> bool:
    return env_enabled(os.environ.get("RANA_TURN_LOGIC_ENABLED"))


def build_rana_special_block(
    user_text: str,
    character: str,
    *,
    session_id: str | None = None,
    is_developer: bool = False,
    **kwargs: object,
) -> str:
    """乐奈本轮特殊指引拼装。

    Args:
        user_text:    当前 turn 的 user message
        character:    角色名（经 registry 归一化的任意别名）
        session_id:   ws session id；用作 per-session 去重 key
        is_developer: True = 本轮对象是开发者（smoke / debug），不触发场景/深模块
        **kwargs:     兼容 caller 传入的 now_jst / ledger / mode / scene_context（本模块不用）

    Returns:
        prompt 片段字符串；无内容时返 ""
    """
    # 名字表只有 registry 一份（见 AGENTS.md）：自带名单会与之漂移，
    # 代价是别名能解析到包、却在包内被判 False 静默返空。
    if canonicalize_name(character) != "乐奈":
        return ""
    if is_developer or not _enabled():
        return ""
    # 主动开口（auto_greet / idle）：user_text 为空，没有可匹配的场景
    if not user_text:
        return ""
    deep_blocks, fired = run_modules(
        _DEEP_MODULES, user_text,
        label="RanaTurnLogic",
        shared_kwargs={"session_id": session_id, "is_developer": is_developer},
        max_blocks=_DEEP_MAX_BLOCKS,
        literal_copy_note=True)
    blocks = list(deep_blocks)
    blocks.extend(build_scene_blocks(
        user_text, uncovered_scenes(RANA_SCENES, fired, _DEEP_SCENE_OVERLAP),
        session_id=session_id, max_blocks=1))
    # 通用场景层（13 个五角色共有的场景）：2026-09-12 新增 `affection`——
    # 被示好不会改变她的说话方式（8 字上下、不给情感回应）。
    append_general_scene_blocks(
        blocks, "乐奈", user_text, label="RanaTurnLogic",
        session_id=session_id, is_developer=is_developer, max_blocks=1)
    return wrap_blocks(blocks)


build_turn_special_block = build_rana_special_block
