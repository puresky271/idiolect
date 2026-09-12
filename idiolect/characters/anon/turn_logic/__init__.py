"""anon.turn_logic — 爱音本轮对话特殊逻辑入口。

设计意图：
  通用 prompt 路径不该堆爱音专属热词触发，爱音专属逻辑集中在这里：

  - **本轮触发**：每次 chat reply 前根据 user_text 判断是否注入特殊指引
  - **窄入口**：只暴露 build_anon_special_block(user_text, character, *, session_id)
  - **可叠加**：内部按场景路由（美妆 / 留学防御 / 灯灯 / sumimi / Ave Mujica / etc.）、
              caller 不需要知道具体分支
  - **可关闭**：env flag `ANON_TURN_LOGIC_ENABLED=0` 一键回退

当前子系统（2026-05-10）：
  · 子系统 1：美妆 / 化妆品（cosmetics.py）— canon 钩子 = 喵梦/若麦 粉丝兴奋
  · 子系统 2：穿搭 / 服装设计（fashion.py）— canon 钩子 = ANON TOKYO（自创品牌+被否决队名）+ 素世「时尚霸凌」
  · 子系统 3：社交平台 / 网络媒体（social_media.py）— canon 钩子 = MyGO SNS 担当（让初华关注 + 跨乐队对照素世 CRYCHIC）
  · 子系统 4：留学失败防御态（london_defense.py）— **心理 canon 不是知识库**、5 motive posture + 1 轮情绪余波
  · 后续按子系统（灯灯 / sumimi / Ave Mujica）逐个加

装配样板（子系统执行 / 通用场景层 / fence 包装 / env 开关语义）统一下沉在
`idiolect.scene_engine`，本文件只声明数据与顺序；子系统走 `lazy_builder`
延迟 import（单模块坏掉只禁用它自己，沿用旧 try/except 的隔离语义）。

注：本模块产物注入到 prompt 补充 slot（供 anon.api
   render_supplemental_blocks 调用）。
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

_PKG = "idiolect.characters.anon.turn_logic"

# ── 子系统层（顺序 = 注入顺序；不封顶、不带反照抄脚注——保持既有输出形态）──
_SUBSYSTEMS = (
    # 子系统 1: 美妆 / 化妆品（3 层渐进激活 + 喵梦/若麦 canon override）
    ("cosmetics", lazy_builder(_PKG, "cosmetics", "build_cosmetics_special_block")),
    # 子系统 2: 穿搭 / 服装设计 / ANON TOKYO（3 层 + 素世「时尚霸凌」双 canon override）
    ("fashion", lazy_builder(_PKG, "fashion", "build_fashion_special_block")),
    # 子系统 3: 社交平台 / 网络媒体 / MyGO SNS 担当（3 层 + canon override）
    ("social_media", lazy_builder(_PKG, "social_media", "build_social_media_special_block")),
    # 子系统 4: 留学失败防御态（心理 canon、5 motive posture + 1 轮情绪余波）
    ("london_defense", lazy_builder(_PKG, "london_defense", "build_london_defense_special_block")),
    # TODO 后续子系统：灯灯 / sumimi / Ave Mujica
)


def _enabled() -> bool:
    return env_enabled(os.environ.get("ANON_TURN_LOGIC_ENABLED"))


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
        character:    角色名（经 registry 归一化的任意别名）
        session_id:   ws session id（可选）— 子系统用作 per-session 去重 key；
                      None → 子系统 fallback 单一 bucket（共享去重状态）
        is_developer: True = 本轮触发对象是**开发者**（smoke / debug / config）、
                      False = 本轮触发对象是**普通用户**（in-canon 对话）。
                      子系统按此区分 framing + 行为：
                        - 标签：cognitive layer 显示「开发者」or「普通用户」
                        - london_defense：dev 不写 / 不消化 residue + 底子放轻 + deep 不真正打开

    Returns:
        prompt 片段字符串、无内容时返 ""
    """
    # 名字表只有 registry 一份（见 AGENTS.md）：自带名单会与之漂移，
    # 代价是别名能解析到包、却在包内被判 False 静默返空。
    if canonicalize_name(character) != "爱音":
        return ""
    if not _enabled():
        return ""
    if not user_text:
        return ""

    blocks, _fired = run_modules(
        _SUBSYSTEMS, user_text,
        label="AnonTurnLogic",
        shared_kwargs={"session_id": session_id, "is_developer": is_developer})

    # ─── 通用场景层（13 个五角色共有的场景） ───
    # 2026-09-12：`affection`（被示好）——爱音的处理方式是用聒噪掩盖、但不承诺。
    append_general_scene_blocks(
        blocks, "爱音", user_text, label="AnonTurnLogic",
        session_id=session_id, is_developer=is_developer, max_blocks=1)

    # 双线包装：每个 block 独立加 ═════ 上下边界、让 LLM 视觉上把它们当独立 fence 看待
    return wrap_blocks(blocks)
