"""tomori.turn_logic — 灯本轮对话特殊逻辑入口。

设计意图：
  灯的歌词逻辑不该耦合在 system prompt 构建路径里，集中在这里：

  - **本轮触发**：每次 chat reply 前根据 user_text 判断是否注入特殊指引
  - **窄入口**：只暴露 build_turn_special_block(user_text, character)
  - **可叠加**：内部按场景路由（lyrics / 笔记本 / 收集物 / 等等）、
              caller 不需要知道具体分支
  - **可关闭**：env flag `TOMORI_TURN_LOGIC_ENABLED=0` 一键回退

当前子系统：
  · text-driven（依赖 user_text）：歌词 / 海洋生物 / 昆虫 / 天文 / 石头
  · time-driven（不依赖 user_text）：凌晨窗口 late_night_window（凌晨 + night_owl_today）

装配样板（子系统执行 / 通用场景层 / fence 包装 / env 开关语义）统一下沉在
`idiolect.scene_engine`，本文件只声明数据与顺序；子系统走 `lazy_builder`
延迟 import（单模块坏掉只禁用它自己，沿用旧 try/except 的隔离语义）。

注：本模块产物注入在 prompt 的 `lyrics_context` slot
（保留这个 key 名向后兼容、内部已不止"歌词"用途）。
"""
from __future__ import annotations

import os

from idiolect.registry import canonicalize_name
from idiolect.scene_engine import (
    append_general_scene_blocks,
    env_enabled,
    lazy_builder,
    run_modules,
    wrap_blocks,
)

_PKG = "idiolect.characters.tomori.turn_logic"

# ── 子系统层（顺序 = 注入顺序；不封顶、不带反照抄脚注——保持既有输出形态）──
_SUBSYSTEMS = (
    ("lyrics", lazy_builder(_PKG, "lyrics", "build_lyrics_special_block")),
    ("marine_life", lazy_builder(_PKG, "marine_life", "build_marine_special_block")),
    ("insects", lazy_builder(_PKG, "insects", "build_insect_special_block")),
    ("astronomy", lazy_builder(_PKG, "astronomy", "build_astronomy_special_block")),
    ("stones", lazy_builder(_PKG, "stones", "build_stone_special_block")),
    ("late_night_window", lazy_builder(_PKG, "late_night_window",
                                       "build_late_night_window_special_block")),
    # TODO 后续子系统：情感语无伦次 / NPC 关系敏感度 / 树叶 / 天气
)
# text-driven 子系统：user_text 为空（autogreet / idle）时不猜话题，跳过
_NEEDS_TEXT = ("lyrics", "marine_life", "insects", "astronomy", "stones")


def _enabled() -> bool:
    return env_enabled(os.environ.get("TOMORI_TURN_LOGIC_ENABLED"))


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
        character:    角色名（经 registry 归一化的任意别名）
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
    # 名字表只有 registry 一份（见 AGENTS.md）：自带名单会与之漂移，
    # 代价是别名能解析到包、却在包内被判 False 静默返空。
    if not _enabled() or canonicalize_name(character) != "灯":
        return ""

    # 各子系统的 kwargs 与旧手写版逐个对齐：lyrics 只收 user_text；
    # late_night_window 额外要 now_jst / ledger / mode（time-driven）。
    _sess_kwargs = {"session_id": session_id, "is_developer": is_developer}
    per_module = {key: dict(_sess_kwargs)
                  for key in ("marine_life", "insects", "astronomy", "stones")}
    per_module["late_night_window"] = {
        **_sess_kwargs, "now_jst": now_jst, "ledger": ledger, "mode": mode,
    }

    blocks, _fired = run_modules(
        _SUBSYSTEMS, user_text,
        label="TomoriTurnLogic",
        shared_kwargs={},
        per_module_kwargs=per_module,
        needs_text=_NEEDS_TEXT)

    # ─── 通用场景层（13 个五角色共有的场景） ───
    # 2026-09-12：`affection`（被示好）实测最差——灯中位 50 字 vs 该场景参照中位 10＝过度铺陈。
    append_general_scene_blocks(
        blocks, "灯", user_text, label="TomoriTurnLogic",
        session_id=session_id, is_developer=is_developer, max_blocks=1)

    # 双线包装：每个 block 独立加 ═════ 上下边界、让 LLM 视觉上把它们当独立 fence 看待
    return wrap_blocks(blocks)
