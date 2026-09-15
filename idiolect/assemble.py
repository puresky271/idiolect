"""最小 prompt 装配器：把四层约束拼成一个可以直接发给模型的 messages 数组。

本仓库只保留「角色怎么说话」这条线，装配顺序是：

  1. 长档案（canon）—— 这个人是谁，说话方式的总纲；
  2. 语气 manifest —— 稳定的句式、口癖、关系差异、反模板化硬约束；
  3. **实测台词基线**（`style_target`）—— 长度 / 句数 / 句末 / 自称的可检验数字，
     命中场景时用该角色在该场景的原作分布；
  4. **turn_logic**（可选）—— 只在命中的轮次注入的场景或主题指引。

这四层就是本项目「蒸馏出来的特征怎么进 prompt」的全部落地形态。
真实系统还可以在前面加记忆与世界状态，但那与本仓库的方法无关。

用法：
    from idiolect.assemble import build_system_prompt, build_messages
    msgs = build_messages("乐奈", "你今天又想去哪找猫")
"""
from __future__ import annotations

from datetime import datetime

from .registry import get_canon_profile, get_voice_manifest, render_turn_special_block
from .scene_classifier import classify
from .style_target import build_style_target_block

# 各层的先后顺序是刻意的：先稳定前缀（canon / manifest），再按轮变化的部分。
# 稳定前缀在前可以让缓存命中，动态块在后不会污染前缀。
LAYER_ORDER = ("canon", "voice", "style_target", "turn_logic")


def _build_layers(
    char: str,
    user_text: str = "",
    *,
    session_id: str | None = None,
    include_turn_logic: bool = True,
    is_developer: bool = False,
    now: datetime | None = None,
) -> dict[str, str]:
    """装配各层并返回 `{层名: 文本}`——`build_system_prompt` 与 `layer_sizes` 的唯一实现。

    诊断值与装配值必须同源（2026-09-13 评审 S1）：以前 `layer_sizes` 自己把
    `classify` / `render_turn_special_block` 重算一遍，两处结果碰巧一致，但任一侧
    改了措辞或条件，尺寸报告就会静默说谎。现在两边都走这里。
    """
    layers: dict[str, str] = {}

    profile = (get_canon_profile(char) or "").strip()
    if profile:
        layers["canon"] = profile

    manifest = (get_voice_manifest(char) or "").strip()
    if manifest:
        layers["voice"] = manifest

    scene = classify(user_text, char) if user_text else ""
    style_block = build_style_target_block(char, scene)
    if style_block:
        layers["style_target"] = style_block

    if include_turn_logic and user_text:
        block = render_turn_special_block(
            char, user_text, session_id=session_id, is_developer=is_developer, mode="chat",
            now_jst=now)
        if block.strip():
            layers["turn_logic"] = block.strip()

    return layers


def build_system_prompt(
    char: str,
    user_text: str = "",
    *,
    session_id: str | None = None,
    include_turn_logic: bool = True,
    is_developer: bool = False,
    now: datetime | None = None,
) -> str:
    """把四层约束拼成 system prompt。缺哪层就跳过哪层。

    `now` 是「现在」的显式入口：turn_logic 里对时间敏感的场景（犯困 / 深夜）
    靠它判定。不传时由下游决定，工具与评测请统一传 `mock_clock.mock_now()`。
    """
    layers = _build_layers(
        char, user_text, session_id=session_id, include_turn_logic=include_turn_logic,
        is_developer=is_developer, now=now)
    return "\n\n".join(layers[k] for k in LAYER_ORDER if k in layers)


def build_messages(
    char: str,
    user_text: str,
    *,
    session_id: str | None = None,
    history: list[dict] | None = None,
    include_turn_logic: bool = True,
    is_developer: bool = False,
    now: datetime | None = None,
) -> list[dict]:
    """返回可直接投喂的 messages：system + history + 本轮 user。"""
    system = build_system_prompt(
        char, user_text, session_id=session_id,
        include_turn_logic=include_turn_logic, is_developer=is_developer, now=now)
    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs.extend(history or [])
    msgs.append({"role": "user", "content": user_text})
    return msgs


def layer_sizes(
    char: str, user_text: str = "", *, session_id: str | None = None,
    include_turn_logic: bool = True, is_developer: bool = False, now: datetime | None = None,
) -> dict[str, int]:
    """各层字符数（诊断用：一眼看出哪一层在撑 prompt）。参数面与 `build_system_prompt` 对齐。

    与装配同源：走同一条 `_build_layers` 路径，报告的永远是装配值本身，
    不再有「诊断自己重算一遍」的分叉隐患。
    """
    from .scene_engine import isolated_session_state

    # 诊断可观察当前会话，但不得消费真实动态模块的去重或计数状态。
    with isolated_session_state():
        layers = _build_layers(
            char, user_text, session_id=session_id, include_turn_logic=include_turn_logic,
            is_developer=is_developer, now=now)
    return {key: len(layers.get(key, "")) for key in LAYER_ORDER}


__all__ = ["LAYER_ORDER", "build_messages", "build_system_prompt", "layer_sizes"]
