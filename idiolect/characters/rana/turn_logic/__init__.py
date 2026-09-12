"""乐奈本轮特殊逻辑入口（仿 tomori / taki / anon turn_logic）。

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

注：本模块产物供 `rana.api.render_supplemental_blocks` 调用、最终注入 system prompt。
"""
from __future__ import annotations

import os
from typing import Callable

from idiolect.registry import canonicalize_name
from idiolect.scene_engine import NO_LITERAL_COPY, SceneModule, build_scene_blocks

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
    raw = os.environ.get("RANA_TURN_LOGIC_ENABLED")
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
            print(f"[RanaTurnLogic/{key}] error: {_err}", flush=True)
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
        return RANA_SCENES
    return [m for m in RANA_SCENES if m.key not in covered]


_BLOCK_BORDER = "═" * 72


def _wrap_blocks(blocks: list[str]) -> str:
    """与 taki 一致的双线包装：让 LLM 把每个 block 当独立 fence。"""
    if not blocks:
        return ""
    wrapped = [f"{_BLOCK_BORDER}\n{b.rstrip()}\n{_BLOCK_BORDER}" for b in blocks if b]
    return "\n\n".join(wrapped)


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
        character:    角色名（兼容多种写法）
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
    deep_blocks, fired = _build_deep_blocks(
        user_text, session_id=session_id, is_developer=is_developer)
    blocks = list(deep_blocks)
    blocks.extend(build_scene_blocks(
        user_text, _scenes_for(fired), session_id=session_id, max_blocks=1))
    # 通用场景层（13 个五角色共有的场景）：2026-09-12 新增 `affection`——
    # 被示好不会改变她的说话方式（8 字上下、不给情感回应）。
    try:
        from idiolect.general_scenes import build_general_scene_blocks
        blocks.extend(build_general_scene_blocks(
            "乐奈", user_text, session_id=session_id, max_blocks=1,
            is_developer=is_developer))
    except Exception as _err:
        print(f"[RanaTurnLogic/general_scenes] error: {_err}", flush=True)
    return _wrap_blocks(blocks)


build_turn_special_block = build_rana_special_block
